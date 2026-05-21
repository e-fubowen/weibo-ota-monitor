"""
weibo_fetcher.py — 微博搜索、翻页、日期过滤
"""
import time
import requests
from datetime import datetime
from functools import wraps

from config import HEADERS, REQUEST_INTERVAL, DATE_START


# ─────────────────────────────────────────────
# 通用重试装饰器
# ─────────────────────────────────────────────
def retry(max_times=3, delay=5):
    """网络请求失败时自动重试。"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_times + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_times:
                        print(f"  [!] {func.__name__} 重试 {max_times} 次仍失败: {e}")
                        return None
                    print(f"  [!] {func.__name__} 第 {attempt} 次失败，{delay}s 后重试: {e}")
                    time.sleep(delay)
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# 日期解析
# ─────────────────────────────────────────────
def parse_date(created_at: str) -> str:
    """将微博时间字符串转为 YYYY-MM-DD HH:MM:SS。"""
    try:
        from email.utils import parsedate
        t = parsedate(created_at)
        return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
    except Exception:
        return "0000-00-00 00:00:00"


# ─────────────────────────────────────────────
# 获取用户昵称
# ─────────────────────────────────────────────
@retry(max_times=3, delay=5)
def get_user_name(uid: int) -> str:
    url = f"https://weibo.com/ajax/profile/info?uid={uid}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    return resp.json().get("data", {}).get("user", {}).get("screen_name", str(uid))


# ─────────────────────────────────────────────
# 搜索微博（含翻页早停）
# ─────────────────────────────────────────────
def search_weibo_by_keyword(uid: int, keyword: str, top_n: int = 10) -> list:
    """
    搜索指定用户主页含关键词的微博。
    当最新一页末尾已早于 DATE_START 时提前停止翻页。
    """
    results, page = [], 1
    dt_start = datetime.strptime(DATE_START, "%Y-%m-%d") if DATE_START else None

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
        print(f"  [i] 第 {page} 页 {len(items)} 条，累计 {len(results)} 条")

        # 早停：本页最后一条已早于起始日期，后续更早无需继续
        if dt_start and items:
            last_date_str = parse_date(items[-1].get("created_at", ""))
            try:
                if datetime.strptime(last_date_str, "%Y-%m-%d") < dt_start:
                    print(f"  [i] 末条日期 {last_date_str} 早于起始日期，停止翻页")
                    break
            except ValueError:
                pass

        total = data.get("data", {}).get("total", 0)
        if len(results) >= top_n or len(results) >= total:
            break

        page += 1
        time.sleep(REQUEST_INTERVAL)

    return results[:top_n]


# ─────────────────────────────────────────────
# 日期过滤
# ─────────────────────────────────────────────
def filter_by_date(weibos: list, start: str | None, end: str | None) -> list:
    """保留发布时间在 [start, end] 区间内的微博。"""
    if not start and not end:
        return weibos

    dt_start = datetime.strptime(start, "%Y-%m-%d") if start else None
    dt_end   = datetime.strptime(end,   "%Y-%m-%d") if end   else None

    filtered = []
    for wb in weibos:
        try:
            dt = datetime.strptime(parse_date(wb.get("created_at", "")), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if dt_start and dt < dt_start:
            continue
        if dt_end and dt > dt_end:
            continue
        filtered.append(wb)

    return filtered
