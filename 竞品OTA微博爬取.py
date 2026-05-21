import os
import requests
import time
import re
import math
import pandas as pd
from PIL import Image
from bs4 import BeautifulSoup
# 使用 RapidOCR（ONNXRuntime 后端，完全绕开 PaddlePaddle/oneDNN，Windows 零问题）
# 安装：pip install rapidocr-onnxruntime
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()

# ================== 配置区 ==================
WEIBO_COOKIE = "SCF=Av6hL9UgUKbq3oy4tjWjFj-8blmK10fETWmbEK6k-nY_PFq01DsGvSj75f--3xFGn6s2NactDnQv53WcMTi3Er8.; UOR=xiaopeng.feishu.cn,weibo.com,xiaopeng.feishu.cn; SINAGLOBAL=9670518676471.285.1773370592305; SUB=_2A25HArGwDeRhGeBN7lsX9yzLwj-IHXVkfkt4rDV8PUNbmtAbLVDQkW9NRFiOS5n-hAnaamIS6IHpwbYgsEXf5O1C; SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WWRTaI8oV2_slHORznL98rD5JpX5KzhUgL.Foq0SK.cS0zN1Ke2dJLoI0MLxKBLB.zL1KnLxK-L12BL1-2LxKqL1KqL1hMLxKML1KBLBKnLxKqL1hnLBoMce0-4SoMES0.0; ALF=02_1781419746; XSRF-TOKEN=7HXV4mw_O3ABxT85I2qyLKkv; _s_tentry=www.weibo.com; Apache=9840460208263.014.1779156847181; ULV=1779156847184:4:3:2:9840460208263.014.1779156847181:1779070205277; WBPSESS=MKc6aAHqUx8kbNTT1MYyoY_Oncp5opsvxF7yFK9IfddDcD1vyYcnlBTaHzz3sUh4H5NalHNDleyVDk91CJHh2sL1g_vVMReFkTDsudw9znDBLf90bJ3A1B-uyXZOAIltuZoYJR0bcTC8mBrJ4fITSg=="

COMPETITOR_UIDS = [
    6192145805,   # 示例：埃安AION
]

SEARCH_KEYWORD   = "OTA"
SEARCH_TOP_N     = 10
REQUEST_INTERVAL = 3

# 所有文件保存在脚本所在目录
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR   = os.path.join(SCRIPT_DIR, "images")
SLICE_DIR   = os.path.join(SCRIPT_DIR, "images", "slices")
OUTPUT_CSV  = os.path.join(SCRIPT_DIR, "ota_monitor.csv")

# 超高图切片参数
MAX_SLICE_HEIGHT = 3000   # 每片高度（px）
SLICE_OVERLAP    = 200    # 相邻切片重叠像素，避免文字被截断
# ============================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Cookie": WEIBO_COOKIE,
    "Referer": "https://weibo.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# ─────────────────────────────────────────────
# 工具：获取用户昵称
# ─────────────────────────────────────────────
def get_user_name(uid: int) -> str:
    url = f"https://weibo.com/ajax/profile/info?uid={uid}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        return resp.json().get("data", {}).get("user", {}).get("screen_name", str(uid))
    except Exception as e:
        print(f"  [!] 获取用户名失败: {e}")
        return str(uid)


# ─────────────────────────────────────────────
# 工具：搜索用户主页关键词微博
# ─────────────────────────────────────────────
def search_weibo_by_keyword(uid: int, keyword: str, top_n: int = 10) -> list:
    results, page = [], 1
    while len(results) < top_n:
        url = (
            f"https://weibo.com/ajax/statuses/searchProfile"
            f"?uid={uid}&page={page}&q={requests.utils.quote(keyword)}&feature=0"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            data = resp.json()
        except Exception as e:
            print(f"  [!] 搜索失败 page={page}: {e}")
            break

        items = data.get("data", {}).get("list", [])
        if not items:
            break
        results.extend(items)
        print(f"  [i] 第{page}页 {len(items)} 条，累计 {len(results)} 条")

        total = data.get("data", {}).get("total", 0)
        if len(results) >= top_n or len(results) >= total:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)

    return results[:top_n]


# ─────────────────────────────────────────────
# 工具：下载图片
# ─────────────────────────────────────────────
def parse_date(created_at: str) -> str:
    """将微博时间字符串（如 Sat May 09 14:50:24 +0800 2026）转为 YYYY-MM-DD。"""
    try:
        from email.utils import parsedate
        t = parsedate(created_at)
        return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"
    except Exception:
        return "0000-00-00"


def download_image(img_url: str, save_name: str) -> str | None:
    """
    下载图片并以 save_name 命名保存（不含扩展名，自动从 URL 取后缀）。
    例：save_name="埃安-2026-05-09-1" → 埃安-2026-05-09-1.jpg
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if img_url.startswith("//"):
        img_url = "https:" + img_url
    # 取原始扩展名（.jpg/.png 等），默认 .jpg
    raw_name = img_url.split("/")[-1].split("?")[0]
    ext = os.path.splitext(raw_name)[1] or ".jpg"
    local_path = os.path.join(IMAGE_DIR, save_name + ext)
    if os.path.exists(local_path):
        return local_path
    try:
        r = requests.get(img_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(r.content)
        return local_path
    except Exception as e:
        print(f"    [!] 下载失败: {e}")
        return None


# ─────────────────────────────────────────────
# ✅ 修复核心：OCR 函数
#   - 使用旧版稳定 API ocr.ocr()
#   - 超高图自动切片，分段识别后拼合
# ─────────────────────────────────────────────
def slice_tall_image(image_path: str) -> list[str]:
    """
    将超高图按 MAX_SLICE_HEIGHT 切成多片，返回切片路径列表。
    普通图片直接返回 [image_path]（不切片）。
    """
    img = Image.open(image_path)
    w, h = img.size

    if h <= MAX_SLICE_HEIGHT:
        return [image_path]   # 不需要切片

    os.makedirs(SLICE_DIR, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    slices = []
    n_slices = math.ceil(h / (MAX_SLICE_HEIGHT - SLICE_OVERLAP))

    for i in range(n_slices):
        top    = max(0, i * (MAX_SLICE_HEIGHT - SLICE_OVERLAP))
        bottom = min(h, top + MAX_SLICE_HEIGHT)
        cropped = img.crop((0, top, w, bottom))
        slice_path = os.path.join(SLICE_DIR, f"{base_name}_s{i:03d}.jpg")
        cropped.save(slice_path, "JPEG", quality=95)
        slices.append(slice_path)
        if bottom >= h:
            break

    print(f"    [i] 超高图 {h}px → 切成 {len(slices)} 片（每片≤{MAX_SLICE_HEIGHT}px）")
    return slices


def ocr_image(image_path: str) -> str:
    """
    对单张图片（或超高图切片后）进行 OCR，返回识别文本。
    RapidOCR 返回：(result, elapse)
      result = [[bbox, text, score], ...] 或 None
    """
    slice_paths = slice_tall_image(image_path)
    all_texts = []

    for sp in slice_paths:
        try:
            result, _ = ocr(sp)
            if not result:
                continue
            for item in result:
                # item: [bbox, text, score]
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text = item[1]
                    if text:
                        all_texts.append(str(text))
        except Exception as e:
            print(f"    [!] OCR 片段失败 {sp}: {e}")

    return "\n".join(all_texts)


# ─────────────────────────────────────────────
# 工具：提取版本号/日期/功能点
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
    date_str = parse_date(created_at)          # YYYY-MM-DD
    print(f"\n  📄 [{created_at}] {text[:60]}...")

    record = {
        "品牌": user_name, "UID": uid,
        "微博ID": wb.get("id", ""), "发布时间": created_at,
        "微博文本": text, "图片数量": 0,
        "图片OCR内容": "", "图片本地路径": "",
        "提取到的版本号": "", "提取到的日期": "", "提取到的功能点": "",
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

        # 命名规则：品牌-YYYY-MM-DD-序号，如 埃安-2026-05-09-1
        save_name = f"{user_name}-{date_str}-{idx}"
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
            print(f"    [i] 图片{idx} 未识别到文字")
        time.sleep(0.5)

    combined_ocr = "\n---\n".join(ocr_texts)
    record["图片OCR内容"] = combined_ocr
    record["图片本地路径"] = "; ".join(local_paths)

    extracted = extract_ota_info(text + "\n" + combined_ocr)
    record["提取到的版本号"] = extracted.get("版本号", "")
    record["提取到的日期"]   = extracted.get("日期", "")
    record["提取到的功能点"] = extracted.get("功能点", "")
    return record


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────
def monitor_all():
    all_results = []
    for uid in COMPETITOR_UIDS:
        user_name = get_user_name(uid)
        print(f"\n{'='*55}")
        print(f"🔍 {user_name}（UID: {uid}）  关键词：{SEARCH_KEYWORD}  取前{SEARCH_TOP_N}条")
        print(f"{'='*55}")

        weibos = search_weibo_by_keyword(uid, SEARCH_KEYWORD, top_n=SEARCH_TOP_N)
        if not weibos:
            print("  ⚠️  未搜到相关微博")
            continue
        print(f"  ✅ 找到 {len(weibos)} 条，开始处理...")

        for i, wb in enumerate(weibos, 1):
            print(f"\n  ── 第 {i}/{len(weibos)} 条 ──")
            all_results.append(process_weibo(wb, user_name, uid))
            time.sleep(REQUEST_INTERVAL)
        time.sleep(REQUEST_INTERVAL)

    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print(f"\n\n📁 完成！已保存 {OUTPUT_CSV}（{len(df)} 条）")
    else:
        print("\n\n📭 未发现 OTA 相关微博。")


if __name__ == "__main__":
    monitor_all()