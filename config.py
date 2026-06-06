"""
config.py — 所有配置集中在这里，其他文件不需要改
"""
import os
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ================== 日志配置 ==================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=LOG_FORMAT,
        datefmt="%H:%M:%S",
    )


# ================== 微博配置 ==================
WEIBO_COOKIE = os.getenv("WEIBO_COOKIE")
if not WEIBO_COOKIE:
    raise ValueError("请在 .env 或环境变量中设置 WEIBO_COOKIE")


COMPETITOR_UIDS = [
    6192145805,  # 埃安AION
]

SEARCH_KEYWORD   = "OTA"
SEARCH_TOP_N     = 10        # 每个品牌最多抓取条数
REQUEST_INTERVAL = 3         # 请求间隔（秒），避免触发风控
MAX_WORKERS      = 3         # 并发品牌数，建议不超过 3

# ================== 日期过滤 ==================
# 格式 YYYY-MM-DD，填 None 则不限制
DATE_START = "2026-03-15"
DATE_END   = "2026-05-15"

# ================== LLM 配置 ==================
LLM_API_KEY  = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL    = os.getenv("LLM_MODEL")

if not LLM_API_KEY or not LLM_BASE_URL or not LLM_MODEL:
    raise ValueError("请在 .env 或环境变量中设置 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL")

LLM_MAX_WEIBO_LENGTH = 300  # 传给 LLM 的微博正文最大字符数
LLM_MAX_OCR_LENGTH   = 3000  # 传给 LLM 的 OCR 内容最大字符数

# ================== 路径配置 ==================
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR  = os.path.join(BASE_DIR, "images")
SLICE_DIR  = os.path.join(BASE_DIR, "images", "slices")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "ota_monitor.csv")

# ================== OCR 配置 ==================
MAX_SLICE_HEIGHT = 3000   # 超高图切片高度（px）
SLICE_OVERLAP    = 200    # 切片重叠像素，避免文字截断
OCR_SLEEP_INTERVAL = 0.5  # 每张图片 OCR 后的休眠秒数
IMAGE_TTL_DAYS = 7        # 下载图片保留天数，超过自动清理

# ================== 请求头 ==================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Cookie": WEIBO_COOKIE,
    "Referer": "https://weibo.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
