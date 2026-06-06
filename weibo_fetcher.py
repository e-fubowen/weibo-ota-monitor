"""
weibo_fetcher.py — 微博搜索、翻页、日期过滤
"""
import logging
import time
import requests
from datetime import datetime
from functools import wraps

from config import HEADERS, REQUEST_INTERVAL, DATE_START

logger = logging.getLogger(__name__)

_session = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


# ─────────────────────────────────────────────
# 通用重试装饰器
# ─────────────────────────────────────────────
def retry(max_times: int = 3, delay: int = 5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_times + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_times:
                        logger.error("%s 重试 %d 次仍失败: %s", func.__name__, max_times, e)
                        return None
                    logger.warning("%s 第 %d 次失败，%ds 后重试: %s", func.__name__, attempt, delay, e)
                    time.sleep(delay)
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# 日期解析
# ─────────────────────────────────────────────
def parse_date(created_at: str) -> str:
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
def get_user_name(uid: int) -> str | None:
    url = f"https://weibo.com/ajax/profile/info?uid={uid}"
    resp = _get_session().get(url, timeout=10)
    return resp.json().get("data", {}).get("user", {}).get("screen_name", str(uid))


# ─────────────────────────────────────────────
# 搜索微博（含翻页早停）
# ─────────────────────────────────────────────
def search_weibo_by_keyword(uid: int, keyword: str, top_n: int = 10) -> list:
    dt_start = datetime.strptime(DATE_START, "%Y-%m-%d") if DATE_START else None
    results, page = [], 1

    while len(results) < top_n:
        url = (
            f"https://weibo.com/ajax/statuses/searchProfile"
            f"?uid={uid}&page={page}&q={requests.utils.quote(keyword)}&feature=0"
        )
        try:
            resp = _get_session().get(url, timeout=10)
            data = resp.json()
        except Exception as e:
            logger.error("搜索失败 page=%d: %s", page, e)
            break

        items = data.get("data", {}).get("list", [])
        if not items:
            break

        results.extend(items)
        logger.info("第 %d 页 %d 条，累计 %d 条", page, len(items), len(results))

        # 早停：本页最后一条已早于起始日期
        if dt_start and items:
            last_date_str = parse_date(items[-1].get("created_at", ""))
            try:
                if datetime.strptime(last_date_str, "%Y-%m-%d") < dt_start:
                    logger.info("末条日期 %s 早于起始日期，停止翻页", last_date_str)
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
