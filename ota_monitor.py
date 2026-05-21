"""
ota_monitor.py — 主入口

运行方式：
    python ota_monitor.py
"""
import os
import re
import time
import threading
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

from config import (
    COMPETITOR_UIDS, SEARCH_KEYWORD, SEARCH_TOP_N,
    DATE_START, DATE_END, REQUEST_INTERVAL, MAX_WORKERS,
    OUTPUT_DIR, OUTPUT_CSV,
)
from weibo_fetcher import get_user_name, search_weibo_by_keyword, filter_by_date, parse_date
from ocr_engine import download_image, ocr_image
from llm_summarizer import summarize_ota
from datetime import datetime

# ─────────────────────────────────────────────
# 线程安全的增量 CSV 写入
# ─────────────────────────────────────────────
_csv_lock = threading.Lock()

def append_to_csv(record: dict):
    """将单条结果线程安全地追加写入 CSV。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with _csv_lock:
        df = pd.DataFrame([record])
        write_header = not os.path.exists(OUTPUT_CSV)
        df.to_csv(OUTPUT_CSV, mode="a", index=False,
                  header=write_header, encoding="utf-8-sig")


# ─────────────────────────────────────────────
# 读取已处理 ID，用于跨次去重
# ─────────────────────────────────────────────
def load_processed_ids() -> set:
    if not os.path.exists(OUTPUT_CSV):
        return set()
    try:
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig", usecols=["微博ID"])
        return set(df["微博ID"].astype(str).tolist())
    except Exception:
        return set()


# ─────────────────────────────────────────────
# 提取 OTA 关键字段（版本号 / 日期 / 功能点）
# ─────────────────────────────────────────────
def extract_ota_info(text: str) -> dict:
    info = {}
    ver = re.search(r'[Vv]?\d+\.\d+(\.\d+)*', text)
    if ver:
        info["版本号"] = ver.group()
    date = re.search(r'(\d{4}[\.\-/年]\d{1,2}[\.\-/月]\d{1,2}[日]?)', text)
    if date:
        info["日期"] = date.group()
    func_kws = ["哨兵模式", "智能驾驶", "语音", "导航", "泊车", "透明底盘", "CarPlay",
                "自动泊车", "高速NOA", "城市NOA", "远程控制", "空调", "地图"]
    funcs = [kw for kw in func_kws if kw in text]
    if funcs:
        info["功能点"] = ", ".join(funcs)
    return info


# ─────────────────────────────────────────────
# 处理单条微博
# ─────────────────────────────────────────────
def process_weibo(wb: dict, user_name: str, uid: int) -> dict:
    text = BeautifulSoup(wb.get("text_raw", ""), "html.parser").get_text()
    created_at = wb.get("created_at", "")
    # 解析原始时间字符串并转换格式
    try:
        parsed_time = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        formatted_time = parsed_time.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        formatted_time = created_at  # 如果解析失败，保持原始格式
    print(f"\n  📄 [{formatted_time}] {text[:60]}...")
    record = {
        "品牌": user_name,
        "UID": uid,
        "微博ID": wb.get("id", ""),
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
        print("    [i] 无图片")
        return record
    ocr_texts, local_paths = [], []
    for idx, pic_info in enumerate(pic_list, 1):
        img_url = (pic_info.get("large", {}).get("url")
                   or pic_info.get("original", {}).get("url")
                   or pic_info.get("url", ""))
        if not img_url:
            continue
        save_name = f"{user_name}-{formatted_time[:10]}-{idx}"
        print(f"    [{idx}/{len(pic_list)}] 📥 下载：{img_url}")
        local_path = download_image(img_url, save_name)
        if not local_path:
            continue
        local_paths.append(local_path)
        ocr_text = ocr_image(local_path)
        if ocr_text:
            ocr_texts.append(f"[图{idx}]\n{ocr_text}")
            print(f"    ✏️  OCR：{ocr_text[:80]}{'...' if len(ocr_text) > 80 else ''}")
        else:
            print(f"    [i] 图片 {idx} 未识别到文字")
        time.sleep(0.5)
    combined_ocr = "\n---\n".join(ocr_texts)
    record["图片OCR内容"]   = combined_ocr
    record["图片本地路径"] = "; ".join(local_paths)
    extracted = extract_ota_info(text + "\n" + combined_ocr)
    record["提取到的版本号"] = extracted.get("版本号", "")
    record["提取到的功能点"] = extracted.get("功能点", "")
    # LLM 结构化总结
    print("    🤖 正在调用 LLM 总结...")
    llm_summary = summarize_ota(user_name, text, combined_ocr)
    record["LLM总结"] = llm_summary
    if llm_summary:
        print(f"    ✅ LLM：{llm_summary[:80]}...")
    return record


# ─────────────────────────────────────────────
# 单品牌完整流程（供线程池调用）
# ─────────────────────────────────────────────
def process_one_brand(uid: int, processed_ids: set) -> int:
    user_name = get_user_name(uid) or str(uid)

    print(f"\n{'='*55}")
    print(f"🔍 {user_name}（UID: {uid}）  关键词：{SEARCH_KEYWORD}  取前 {SEARCH_TOP_N} 条")
    print(f"📅 日期范围：{DATE_START or '不限'} ～ {DATE_END or '不限'}")
    print(f"{'='*55}")

    weibos = search_weibo_by_keyword(uid, SEARCH_KEYWORD, top_n=SEARCH_TOP_N)
    weibos = filter_by_date(weibos, DATE_START, DATE_END)

    if not weibos:
        print(f"  ⚠️  {DATE_START} ～ {DATE_END} 范围内未搜到相关微博：无")
        return 0

    # 去重：跳过已处理过的微博
    new_weibos = [wb for wb in weibos if str(wb.get("id", "")) not in processed_ids]
    skipped = len(weibos) - len(new_weibos)
    if skipped:
        print(f"  [i] 跳过已处理 {skipped} 条，新增 {len(new_weibos)} 条")
    if not new_weibos:
        print("  [i] 无新增条目")
        return 0

    print(f"  ✅ 共 {len(new_weibos)} 条待处理...")
    count = 0
    for i, wb in enumerate(new_weibos, 1):
        print(f"\n  ── {user_name} 第 {i}/{len(new_weibos)} 条 ──")
        record = process_weibo(wb, user_name, uid)
        append_to_csv(record)
        count += 1
        time.sleep(REQUEST_INTERVAL)

    return count


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────
def monitor_all():
    processed_ids = load_processed_ids()
    if processed_ids:
        print(f"[i] 检测到历史记录，将跳过已处理的 {len(processed_ids)} 条微博")

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
                print(f"  [!] UID {uid} 处理异常: {e}")

    if total_written:
        print(f"\n\n📁 完成！本次新写入 {total_written} 条 → {OUTPUT_CSV}")
    else:
        print("\n\n📭 无")


if __name__ == "__main__":
    monitor_all()
