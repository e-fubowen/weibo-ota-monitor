"""
ocr_engine.py — 图片下载、超高图切片、OCR 识别
"""
import os
import math
import time
import requests
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from config import HEADERS, IMAGE_DIR, SLICE_DIR, MAX_SLICE_HEIGHT, SLICE_OVERLAP
from weibo_fetcher import retry

ocr = RapidOCR()


# ─────────────────────────────────────────────
# 下载图片
# ─────────────────────────────────────────────
@retry(max_times=3, delay=5)
def download_image(img_url: str, save_name: str) -> str | None:
    """
    下载图片，以 save_name 命名（不含扩展名）保存到 IMAGE_DIR。
    文件已存在时直接返回本地路径，不重复下载。
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if img_url.startswith("//"):
        img_url = "https:" + img_url

    raw_name = img_url.split("/")[-1].split("?")[0]
    ext = os.path.splitext(raw_name)[1] or ".jpg"
    local_path = os.path.join(IMAGE_DIR, save_name + ext)

    if os.path.exists(local_path):
        return local_path

    r = requests.get(img_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(r.content)
    return local_path


# ─────────────────────────────────────────────
# 超高图切片
# ─────────────────────────────────────────────
def slice_tall_image(image_path: str) -> list[str]:
    """
    图片高度超过 MAX_SLICE_HEIGHT 时按片切割，返回切片路径列表。
    普通高度图片直接返回 [image_path]。
    """
    img = Image.open(image_path)
    w, h = img.size

    if h <= MAX_SLICE_HEIGHT:
        return [image_path]

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

    print(f"    [i] 超高图 {h}px → 切成 {len(slices)} 片（每片 ≤ {MAX_SLICE_HEIGHT}px）")
    return slices


# ─────────────────────────────────────────────
# OCR 识别
# ─────────────────────────────────────────────
def ocr_image(image_path: str) -> str:
    """对单张图片（含超高图自动切片）进行 OCR，返回识别文本。"""
    slice_paths = slice_tall_image(image_path)
    all_texts = []

    for sp in slice_paths:
        try:
            result, _ = ocr(sp)
            if not result:
                continue
            for item in result:
                if isinstance(item, (list, tuple)) and len(item) >= 2 and item[1]:
                    all_texts.append(str(item[1]))
        except Exception as e:
            print(f"    [!] OCR 片段失败 {sp}: {e}")

    return "\n".join(all_texts)
