"""
writer.py — CSV 写入与历史去重（兼容旧数据结构版）
"""
import logging
import os
import threading

import pandas as pd

logger = logging.getLogger(__name__)

_csv_lock = threading.Lock()


# ─────────────────────────────────────────────
# 加载已处理微博ID（兼容旧CSV结构）
# ─────────────────────────────────────────────
def load_processed_ids(csv_path: str) -> set:
    if not os.path.exists(csv_path):
        return set()

    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")

        # 兼容：如果没有微博链接列，直接跳过
        if "微博链接" not in df.columns:
            logger.warning("历史CSV无【微博链接】列，跳过去重（仅本次运行）")
            return set()

        processed = set()

        for link in df["微博链接"].dropna().astype(str):
            link = link.strip()

            # 容错：空值/非法值
            if not link:
                continue

            # 从 URL 中提取微博ID
            parts = link.split("/")
            if not parts:
                continue

            weibo_id = parts[-1]
            if weibo_id.isdigit():
                processed.add(weibo_id)

        return processed

    except Exception as e:
        logger.warning("读取历史记录失败: %s", e)
        return set()


# ─────────────────────────────────────────────
# 写入CSV（追加模式 + 自动创建目录）
# ─────────────────────────────────────────────
def write_records(csv_path: str, records: list[dict]) -> None:
    if not records:
        return

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with _csv_lock:
        df = pd.DataFrame(records)

        # 首次写入才写表头
        write_header = not os.path.exists(csv_path)

        df.to_csv(
            csv_path,
            mode="a",
            index=False,
            header=write_header,
            encoding="utf-8-sig"
        )

    logger.info("已写入 %d 条记录 → %s", len(records), csv_path)