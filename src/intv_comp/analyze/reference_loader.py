"""
追加資料（参考資料）の読み込みモジュール。

法制審議会の議事録等の追加資料をファイルシステムから読み込み、
LLMに提供するための機能を提供する。
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from intv_comp.logger import logger


def load_reference_materials(references_dir: Path) -> str:
    """
    指定されたディレクトリから追加資料を読み込み、結合したテキストを返す。

    Args:
        references_dir: 追加資料が格納されているディレクトリのパス

    Returns:
        読み込んだ全ての資料を結合したテキスト。資料がない場合は空文字列。
    """
    if not references_dir.exists():
        logger.info(f"追加資料のディレクトリが存在しません: {references_dir}")
        return ""

    if not references_dir.is_dir():
        logger.warning(f"指定されたパスはディレクトリではありません: {references_dir}")
        return ""

    # サポートされる拡張子
    supported_extensions = {".txt", ".md"}

    # ファイルを収集
    reference_files: List[Path] = []
    for ext in supported_extensions:
        reference_files.extend(references_dir.glob(f"*{ext}"))

    if not reference_files:
        logger.info(f"追加資料が見つかりませんでした: {references_dir}")
        return ""

    # ファイルを読み込んで結合
    materials: List[str] = []
    for file_path in sorted(reference_files):
        try:
            content = file_path.read_text(encoding="utf-8")
            materials.append(f"# {file_path.name}\n\n{content}")
            logger.info(f"追加資料を読み込みました: {file_path.name}")
        except Exception as exc:
            logger.warning(f"資料の読み込みに失敗しました: {file_path.name} - {exc}")
            continue

    if not materials:
        logger.info("読み込み可能な追加資料がありませんでした")
        return ""

    combined_text = "\n\n---\n\n".join(materials)
    logger.info(f"{len(materials)}件の追加資料を読み込みました")
    return combined_text
