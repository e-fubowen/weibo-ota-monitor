"""
config.py — 所有配置集中在这里，其他文件不需要改
"""
import os

# ================== 微博配置 ==================
WEIBO_COOKIE = "SCF=Av6hL9UgUKbq3oy4tjWjFj-8blmK10fETWmbEK6k-nY_PFq01DsGvSj75f--3xFGn6s2NactDnQv53WcMTi3Er8.; UOR=xiaopeng.feishu.cn,weibo.com,xiaopeng.feishu.cn; SINAGLOBAL=9670518676471.285.1773370592305; SUB=_2A25HArGwDeRhGeBN7lsX9yzLwj-IHXVkfkt4rDV8PUNbmtAbLVDQkW9NRFiOS5n-hAnaamIS6IHpwbYgsEXf5O1C; SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WWRTaI8oV2_slHORznL98rD5JpX5KzhUgL.Foq0SK.cS0zN1Ke2dJLoI0MLxKBLB.zL1KnLxK-L12BL1-2LxKqL1KqL1hMLxKML1KBLBKnLxKqL1hnLBoMce0-4SoMES0.0; ALF=02_1781419746; XSRF-TOKEN=7HXV4mw_O3ABxT85I2qyLKkv; _s_tentry=www.weibo.com; Apache=9840460208263.014.1779156847181; ULV=1779156847184:4:3:2:9840460208263.014.1779156847181:1779070205277; WBPSESS=MKc6aAHqUx8kbNTT1MYyoY_Oncp5opsvxF7yFK9IfddDcD1vyYcnlBTaHzz3sUh4H5NalHNDleyVDk91CJHh2sL1g_vVMReFkTDsudw9znDBLf90bJ3A1B-uyXZOAIltuZoYJR0bcTC8mBrJ4fITSg=="


COMPETITOR_UIDS = [
    6192145805,  # 埃安AION
    # 3032210184,  # 鸿蒙智行
    # 7871239944,  # 小米汽车
    # 6001272153,  # 理想汽车
    # 5675889356,  # 蔚来
    # 继续添加竞品 UID
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
# 选一个平台填入，其余注释掉

# ① 硅基流动（推荐：国内直连，注册地址 https://cloud.siliconflow.cn）
# LLM_API_KEY  = "sk-vtnwihighnhcldljbrypbhngxszezaanaeyizlernuriprqy"
# LLM_BASE_URL = "https://api.siliconflow.cn/v1"
# LLM_MODEL    = "deepseek-ai/DeepSeek-V3"

# ② 智谱 GLM-4（永久免费，注册地址 https://open.bigmodel.cn）
LLM_API_KEY  = "73ac9ae851894ad0b69c4a4f164c5204.XRvBtsUf3S5yX2sq"
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
LLM_MODEL    = "glm-4-flash"

# ③ Google Gemini（1500次/天，需翻墙，注册地址 https://aistudio.google.com）
# LLM_API_KEY  = "AIzaxxxxxxxx"
# LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
# LLM_MODEL    = "gemini-2.5-flash"

# ================== 路径配置 ==================
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR  = os.path.join(BASE_DIR, "images")
SLICE_DIR  = os.path.join(BASE_DIR, "images", "slices")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "ota_monitor.csv")

# ================== OCR 配置 ==================
MAX_SLICE_HEIGHT = 3000   # 超高图切片高度（px）
SLICE_OVERLAP    = 200    # 切片重叠像素，避免文字截断

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
