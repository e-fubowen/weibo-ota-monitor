"""
extractor.py — 从微博文本 + OCR 结果中提取 OTA 关键字段
"""
import re

# OTA 功能点关键词
_FUNC_KEYWORDS = [
    "哨兵模式", "智能驾驶", "语音", "导航", "泊车", "透明底盘", "CarPlay",
    "自动泊车", "高速NOA", "城市NOA", "远程控制", "空调", "地图",
]


def extract_ota_info(text: str) -> dict:
    info = {}
    ver = re.search(r'[Vv]?\d+\.\d+(\.\d+)*', text)
    if ver:
        info["版本号"] = ver.group()
    date = re.search(r'(\d{4}[\.\-/年]\d{1,2}[\.\-/月]\d{1,2}[日]?)', text)
    if date:
        info["日期"] = date.group()
    funcs = [kw for kw in _FUNC_KEYWORDS if kw in text]
    if funcs:
        info["功能点"] = ", ".join(funcs)
    return info
