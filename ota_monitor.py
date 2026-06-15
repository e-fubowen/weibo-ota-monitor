"""
ota_monitor.py — 主入口

运行方式：
    python ota_monitor.py
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from bs4 import BeautifulSoup

from config import (
    COMPETITOR_UIDS,
    DATE_END,
    DATE_START,
    MAX_WORKERS,
    OUTPUT_CSV,
    REQUEST_INTERVAL,
    SEARCH_KEYWORD,
    SEARCH_TOP_N,
    setup_logging,
    validate,
)
from extractor import extract_ota_info
from llm_summarizer import summarize_ota
from ocr_engine import cleanup_old_images, download_image, ocr_image
from weibo_fetcher import filter_by_date, get_user_name, search_weibo_by_keyword
from writer import load_processed_ids, write_records

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 处理单条微博
# ─────────────────────────────────────────────
def process_weibo(wb: dict, user_name: str, uid: int) -> dict:
    text = BeautifulSoup(wb.get("text_raw", ""), "html.parser").get_text()
    created_at = wb.get("created_at", "")
    try:
        parsed_time = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        formatted_time = parsed_time.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        formatted_time = created_at

    weibo_id = str(wb.get("id", ""))
    weibo_link = f"https://weibo.com/{uid}/{weibo_id}" if uid and weibo_id else ""

    logger.info("[%s] %s...", formatted_time, text[:60])

    record = {
        "品牌": user_name,
        "微博链接": weibo_link,
        "发布时间": formatted_time,
        "微博文本": text,
        "图片数量": 0,
        "图片OCR内容": "",
        "图片本地路径": "",
        "提取到的版本号": "",
        "提取到的功能点": "",
        "LLM总结": "",
    }

    pics_raw = wb.get("pic_infos") or wb.get("pics", [])
    pic_list = list(pics_raw.values()) if isinstance(pics_raw, dict) else pics_raw
    record["图片数量"] = len(pic_list)

    if not pic_list:
        logger.info("无图片")
        return record

    ocr_texts, local_paths = [], []
    for idx, pic_info in enumerate(pic_list, 1):
        img_url = (pic_info.get("large", {}).get("url")
                   or pic_info.get("original", {}).get("url")
                   or pic_info.get("url", ""))
        if not img_url:
            continue

        save_name = f"{user_name}-{formatted_time[:10]}-{idx}"
        logger.info("[%d/%d] 下载：%s", idx, len(pic_list), img_url)
        local_path = download_image(img_url, save_name)
        if not local_path:
            continue
        local_paths.append(local_path)

        ocr_text = ocr_image(local_path)
        if ocr_text:
            ocr_texts.append(f"[图{idx}]\n{ocr_text}")
            logger.info("OCR：%s...", ocr_text[:80])
        else:
            logger.info("图片 %d 未识别到文字", idx)
        time.sleep(0.5)

    combined_ocr = "\n---\n".join(ocr_texts)
    record["图片OCR内容"] = combined_ocr
    record["图片本地路径"] = "; ".join(local_paths)

    extracted = extract_ota_info(text + "\n" + combined_ocr)
    record["提取到的版本号"] = extracted.get("版本号", "")
    record["提取到的功能点"] = extracted.get("功能点", "")

    logger.info("正在调用 LLM 总结...")
    result = summarize_ota(user_name, text, combined_ocr)
    record["LLM总结"] = result.content
    if result.success:
        logger.info("LLM：%s...", result.content[:80])
        if result.missing_fields:
            logger.warning("LLM 输出缺少字段：%s", result.missing_fields)
    else:
        logger.warning("LLM 总结失败：%s", result.error)

    return record


# ─────────────────────────────────────────────
# 处理单个品牌
# ─────────────────────────────────────────────
def process_one_brand(uid: int, processed_ids: set) -> int:
    user_name = get_user_name(uid) or str(uid)

    logger.info("=" * 55)
    logger.info("%s（UID: %d）  关键词：%s  取前 %d 条", user_name, uid, SEARCH_KEYWORD, SEARCH_TOP_N)
    logger.info("日期范围：%s ～ %s", DATE_START or "不限", DATE_END or "不限")
    logger.info("=" * 55)

    weibos = search_weibo_by_keyword(uid, SEARCH_KEYWORD, top_n=SEARCH_TOP_N)
    weibos = filter_by_date(weibos, DATE_START, DATE_END)

    if not weibos:
        logger.warning("%s ～ %s 范围内未搜到相关微博", DATE_START, DATE_END)
        return 0

    new_weibos = [wb for wb in weibos if str(wb.get("id", "")) not in processed_ids]
    skipped = len(weibos) - len(new_weibos)
    if skipped:
        logger.info("跳过已处理 %d 条，新增 %d 条", skipped, len(new_weibos))
    if not new_weibos:
        logger.info("无新增条目")
        return 0

    logger.info("共 %d 条待处理...", len(new_weibos))
    records = []
    for i, wb in enumerate(new_weibos, 1):
        logger.info("── %s 第 %d/%d 条 ──", user_name, i, len(new_weibos))
        record = process_weibo(wb, user_name, uid)
        records.append(record)
        time.sleep(REQUEST_INTERVAL)

    write_records(OUTPUT_CSV, records)
    return len(records)


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────
def monitor_all():
    setup_logging()
    validate()
    logger.info("启动 OTA 监控...")

    cleanup_old_images()

    processed_ids = load_processed_ids(OUTPUT_CSV)
    if processed_ids:
        logger.info("检测到历史记录，将跳过已处理的 %d 条微博", len(processed_ids))

    total_written = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_one_brand, uid, processed_ids): uid
            for uid in COMPETITOR_UIDS
        }
        for future in as_completed(futures):
            uid = futures[future]
            try:
                n = future.result()
                total_written += n
            except Exception as e:
                logger.error("UID %d 处理异常: %s", uid, e)

    if total_written:
        logger.info("完成！本次新写入 %d 条 → %s", total_written, OUTPUT_CSV)
    else:
        logger.info("无新增数据")


if __name__ == "__main__":
    monitor_all()