"""
config.py — 所有配置集中在这里，其他文件不需要改
"""
import logging
import os
import sys

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
        stream=sys.stdout,
    )


# ================== 微博配置 ==================
WEIBO_COOKIE = os.getenv("WEIBO_COOKIE", "")

COMPETITOR_UIDS = [
#广汽
# 6192145805,  # 埃安AION
# 1674122465,  # 传祺
# #大众
# 1881301247, # 大众
# 6893624593, # 捷达
# 1841218153, # 奥迪
# #通用集团
# 1667553532, #别克
# 1667554942, #凯迪拉克
# 1743347041, #雪佛兰
# #东风集团
# 7351024207, #岚图
# 7829715138, #东风奕派
# 1739840253, #东风风神
# 1812448064, #东风风行
# 7540303177, #东风奕派纳米
#
# 7579335866, #上汽奥迪
# #Stellantis集团
# 1723888554, #雪铁龙
# 1740623531, #东风标志
# 7985359310 ,#东风示界
# #福特集团
# 1651046593, #福特
# 5035483816, #林肯
#
# 1666454854, #梅赛德斯-奔驰
# 1667486960, #smart
# 3615027564, #特斯拉
# 1698264705, #宝马
# 1647951825, #广汽丰田
# 2286596480, #一汽丰田
# 1912067745, #本田
# 1932891383, #日产
# 2101359450, #启辰
# 1740307755, #马自达
# 2335953143, #北京现代
# 3634148760, #五菱银标
# 7351032671, #宝骏
# 1768037090, #五菱
# 3266910853, #一汽红旗
# 1749965754, #一汽奔腾
# 7545341480, #智己汽车
# 6334228193, #飞凡汽车
# 1716643487, #荣威汽车
# 2005342162, #奇瑞
# 7868826786, #奇瑞风云
# 6437850992, #捷途
# 6821334172, #星途
# 7623544774, #ICAR
# 3194397971, #长安启源
# 7751244203, #深蓝汽车
# 1888373567, #哈弗SUV
# 6055831093, #魏牌
# 6505869401, #欧拉汽车
# 7582509920, #坦克
# 1974658370, #长城炮
# 7794864065, #吉利银河
# 7576049404, #极氪
# 6031625275, #领克



]

SEARCH_KEYWORD   = "OTA"
SEARCH_TOP_N     = 10        # 每个品牌最多抓取条数
REQUEST_INTERVAL = 3         # 请求间隔（秒），避免触发风控
MAX_WORKERS      = 3         # 并发品牌数，建议不超过 3

# ================== 日期过滤 ==================
# 格式 YYYY-MM-DD，填 None 则不限制
DATE_START = "2026-05-15"
DATE_END   = "2026-06-15"

# ================== LLM 配置 ==================
LLM_API_KEY  = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL    = os.getenv("LLM_MODEL", "")


def validate():
    """运行时校验必要配置，避免模块导入时直接报错。"""
    if not WEIBO_COOKIE:
        raise ValueError("请在 .env 或环境变量中设置 WEIBO_COOKIE")
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
