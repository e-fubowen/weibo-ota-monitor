"""
writer.py — CSV 写入与历史去重
"""
import os
import logging
import threading

import pandas as pd

logger = logging.getLogger(__name__)

_csv_lock = threading.Lock()


def load_processed_ids(csv_path: str) -> set:
    if not os.path.exists(csv_path):
        return set()
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig", usecols=["微博链接"])
        processed = set()
        for link in df["微博链接"].astype(str):
            parts = link.strip().split("/")
            if parts:
                weibo_id = parts[-1]
                if weibo_id.isdigit():
                    processed.add(weibo_id)
        return processed
    except Exception as e:
        logger.warning("读取历史记录失败: %s", e)
        return set()


def write_records(csv_path: str, records: list[dict]) -> None:
    if not records:
        return
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with _csv_lock:
        df = pd.DataFrame(records)
        write_header = not os.path.exists(csv_path)
        df.to_csv(csv_path, mode="a", index=False,
                  header=write_header, encoding="utf-8-sig")
    logger.info("已写入 %d 条记录 → %s", len(records), csv_path)
