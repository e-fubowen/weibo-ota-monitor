"""
ocr_engine.py — 图片下载、超高图切片、OCR 识别
"""
import logging
import os
import math
import time
import requests
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from config import (
    HEADERS, IMAGE_DIR, SLICE_DIR,
    MAX_SLICE_HEIGHT, SLICE_OVERLAP, OCR_SLEEP_INTERVAL, IMAGE_TTL_DAYS,
)
from weibo_fetcher import retry

logger = logging.getLogger(__name__)

_ocr = None


def _get_ocr() -> RapidOCR:
    global _ocr
    if _ocr is None:
        _ocr = RapidOCR()
    return _ocr


# ─────────────────────────────────────────────
# 下载图片
# ─────────────────────────────────────────────
@retry(max_times=3, delay=5)
def download_image(img_url: str, save_name: str) -> str | None:
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

    logger.info("超高图 %dpx → 切成 %d 片", h, len(slices))
    return slices


# ─────────────────────────────────────────────
# 单切片 OCR（含重试）
# ─────────────────────────────────────────────
@retry(max_times=2, delay=3)
def _ocr_single(slice_path: str) -> list[str]:
    result, _ = _get_ocr()(slice_path)
    if not result:
        return []
    texts = []
    for item in result:
        if isinstance(item, (list, tuple)) and len(item) >= 2 and item[1]:
            texts.append(str(item[1]))
    return texts


# ─────────────────────────────────────────────
# 内部去重（移除 OCR 重复行）
# ─────────────────────────────────────────────
def _dedup_lines(lines: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for line in lines:
        s = line.strip()
        if s and s not in seen:
            deduped.append(s)
            seen.add(s)
    return deduped


# ─────────────────────────────────────────────
# OCR 识别（含自动切片 + 去重）
# ─────────────────────────────────────────────
def ocr_image(image_path: str) -> str:
    slice_paths = slice_tall_image(image_path)
    all_texts = []

    for sp in slice_paths:
        try:
            texts = _ocr_single(sp)
            all_texts.extend(texts)
        except Exception as e:
            logger.error("OCR 片段失败 %s: %s", sp, e)
        time.sleep(OCR_SLEEP_INTERVAL)

    all_texts = _dedup_lines(all_texts)
    return "\n".join(all_texts)


# ─────────────────────────────────────────────
# 清理过期图片
# ─────────────────────────────────────────────
def cleanup_old_images(ttl_days: int = IMAGE_TTL_DAYS) -> None:
    now = time.time()
    for directory in (IMAGE_DIR, SLICE_DIR):
        if not os.path.exists(directory):
            continue
        for fname in os.listdir(directory):
            fpath = os.path.join(directory, fname)
            if os.path.isfile(fpath):
                age = now - os.path.getmtime(fpath)
                if age > ttl_days * 86400:
                    os.remove(fpath)
                    logger.info("清理过期图片: %s", fpath)
