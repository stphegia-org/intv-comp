"""Loguruのロガー設定モジュール."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logger(log_dir: Path | None = None) -> None:
    """Loguruロガーの設定を行う.

    標準出力への出力と、ログファイルへの出力を同時に行う設定を行う.
    ログファイルは１日単位でローテーションする（ローカルタイムを使用）.

    Args:
        log_dir: ログファイルを保存するディレクトリ. Noneの場合はデフォルトでlogsディレクトリを使用.
    """
    # デフォルトのロガーを削除
    logger.remove()

    # 標準出力への出力を追加
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    # ログディレクトリの設定
    if log_dir is None:
        log_dir = Path("logs")

    # ログディレクトリが存在しない場合は作成
    log_dir.mkdir(parents=True, exist_ok=True)

    # ログファイルへの出力を追加（日次ローテーション）
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",  # 毎日0時にローテーション（ローカルタイム）
        retention="30 days",  # 30日間保持
        encoding="utf-8",
    )


# ロガーをエクスポート
__all__ = ["logger", "setup_logger"]
