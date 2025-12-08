"""
外部情報参照リスト（external sources）の読み込みと管理モジュール。

このモジュールは、インタビュー分析で引用される際に、
外部公開URLを付与するための情報を管理します。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from intv_comp.logger import logger


@dataclass
class ExternalDocument:
    """外部文書情報を保持するデータクラス。"""

    doc_id: str
    title: str
    url: str
    description: str


@dataclass
class SessionDocumentMapping:
    """セッションIDと関連文書のマッピング情報を保持するデータクラス。"""

    session_id: str
    related_doc_ids: List[str]
    description: str


class ExternalSourcesRepository:
    """外部情報参照リストを管理するリポジトリクラス。"""

    def __init__(self) -> None:
        """初期化処理。"""
        self.documents: Dict[str, ExternalDocument] = {}
        self.session_mappings: Dict[str, SessionDocumentMapping] = {}

    def add_document(self, document: ExternalDocument) -> None:
        """外部文書を追加する。

        Args:
            document: 追加する外部文書情報
        """
        self.documents[document.doc_id] = document

    def add_session_mapping(self, mapping: SessionDocumentMapping) -> None:
        """セッションと文書のマッピングを追加する。

        Args:
            mapping: セッションマッピング情報
        """
        self.session_mappings[mapping.session_id] = mapping

    def get_document(self, doc_id: str) -> ExternalDocument | None:
        """文書IDから外部文書情報を取得する。

        Args:
            doc_id: 文書ID

        Returns:
            外部文書情報。見つからない場合はNone
        """
        return self.documents.get(doc_id)

    def get_documents_for_session(self, session_id: str) -> List[ExternalDocument]:
        """セッションIDに関連する外部文書のリストを取得する。

        Args:
            session_id: セッションID

        Returns:
            関連する外部文書のリスト
        """
        mapping = self.session_mappings.get(session_id)
        if not mapping:
            return []

        documents = []
        for doc_id in mapping.related_doc_ids:
            doc = self.get_document(doc_id)
            if doc:
                documents.append(doc)
        return documents

    def get_primary_url_for_session(self, session_id: str) -> str:
        """セッションの主要な参照URLを取得する。

        Args:
            session_id: セッションID

        Returns:
            主要な参照URL。見つからない場合は空文字列
        """
        docs = self.get_documents_for_session(session_id)
        if docs:
            return docs[0].url
        return ""


def parse_external_sources_markdown(content: str) -> ExternalSourcesRepository:
    """Markdown形式の外部情報参照リストをパースする。

    Args:
        content: Markdown形式のテキスト

    Returns:
        パースされた外部情報リポジトリ
    """
    repo = ExternalSourcesRepository()

    # 文書情報のパース
    # パターン: - **文書ID**: DOC001 の後に続く情報を取得
    doc_pattern = re.compile(
        r"-\s*\*\*文書ID\*\*:\s*(?P<doc_id>\S+).*?"
        r"-\s*\*\*タイトル\*\*:\s*(?P<title>.+?)(?=\n).*?"
        r"-\s*\*\*URL\*\*:\s*(?P<url>\S+).*?"
        r"-\s*\*\*説明\*\*:\s*(?P<description>.+?)(?=\n)",
        re.DOTALL | re.MULTILINE,
    )

    for match in doc_pattern.finditer(content):
        doc = ExternalDocument(
            doc_id=match.group("doc_id").strip(),
            title=match.group("title").strip(),
            url=match.group("url").strip(),
            description=match.group("description").strip(),
        )
        repo.add_document(doc)
        logger.debug(
            "外部文書を読み込みました: {} ({})",
            doc.doc_id,
            doc.title,
        )

    # セッションマッピングのパース
    # パターン: ### セッション: {session_id} の後に続く情報を取得
    session_pattern = re.compile(
        r"###\s*セッション:\s*(?P<session_id>\S+).*?"
        r"-\s*\*\*関連文書\*\*:\s*(?P<doc_ids>.+?)(?=\n).*?"
        r"-\s*\*\*説明\*\*:\s*(?P<description>.+?)(?=\n)",
        re.DOTALL | re.MULTILINE,
    )

    for match in session_pattern.finditer(content):
        session_id = match.group("session_id").strip()
        doc_ids_str = match.group("doc_ids").strip()
        description = match.group("description").strip()

        # カンマ区切りで文書IDをパース
        doc_ids = [doc_id.strip() for doc_id in doc_ids_str.split(",")]

        mapping = SessionDocumentMapping(
            session_id=session_id,
            related_doc_ids=doc_ids,
            description=description,
        )
        repo.add_session_mapping(mapping)
        logger.debug(
            "セッションマッピングを読み込みました: {} -> {}",
            session_id,
            ", ".join(doc_ids),
        )

    logger.info(
        "外部情報参照リストを読み込みました: 文書{}件、セッションマッピング{}件",
        len(repo.documents),
        len(repo.session_mappings),
    )

    return repo


def load_external_sources(file_path: Path) -> ExternalSourcesRepository:
    """外部情報参照リストファイルを読み込む。

    Args:
        file_path: 外部情報参照リストファイルのパス

    Returns:
        外部情報リポジトリ

    Raises:
        FileNotFoundError: ファイルが見つからない場合
    """
    if not file_path.exists():
        logger.warning("外部情報参照リストが見つかりません: {}", file_path)
        return ExternalSourcesRepository()

    try:
        content = file_path.read_text(encoding="utf-8")
        return parse_external_sources_markdown(content)
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("外部情報参照リストの読み込みに失敗しました: {} - {}", file_path, exc)
        return ExternalSourcesRepository()
