"""メッセージの関連度フィルタリング機能を提供するモジュール。

法案や対象業務に関連しないメッセージを除外するためのスコアリングとフィルタリングを行う。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from intv_comp.logger import logger

if TYPE_CHECKING:
    import pandas as pd

# 法案・業務関連度スコアの閾値（この値以下のメッセージは除外される）
# 調整可能: 0.0～1.0 の範囲で設定。低いほど厳しくフィルタリングされる
DEFAULT_RELEVANCE_THRESHOLD = 0.3

# 法案・政策・対象業務に関連するキーワードリスト
# これらのキーワードが含まれる発言は関連度が高いと判断される
BILL_RELATED_KEYWORDS = [
    # 法案・制度関連
    "法案",
    "法律",
    "制度",
    "規制",
    "政策",
    "法整備",
    "立法",
    "条文",
    "改正",
    "施行",
    # 船荷証券・貿易関連
    "船荷証券",
    "B/L",
    "BL",
    "bill of lading",
    "電子化",
    "デジタル化",
    "ペーパーレス",
    "貿易",
    "輸出",
    "輸入",
    "通関",
    "税関",
    "荷主",
    "運送",
    "船会社",
    "フォワーダー",
    "物流",
    "国際取引",
    # 業務・実務関連
    "実務",
    "業務",
    "手続き",
    "作業",
    "プロセス",
    "フロー",
    "運用",
    "システム",
    "セキュリティ",
    "リスク",
    "コスト",
    "効率",
    # 問題・課題関連
    "課題",
    "問題",
    "懸念",
    "不安",
    "改善",
    "提案",
    "対策",
    "検討",
    # 意見・評価関連
    "賛成",
    "反対",
    "必要",
    "不要",
    "有効",
    "無効",
]

# キーワードマッチング用の事前コンパイルされた正規表現パターン
# パフォーマンス向上のため、各キーワードのパターンと小文字版を事前にコンパイル
# タプル形式: (元のキーワード, 小文字版, パターン)
_KEYWORD_PATTERNS: list[tuple[str, str, re.Pattern[str] | None]] = []


def _build_keyword_patterns() -> None:
    """キーワードマッチング用のパターンを構築する（初回のみ実行）。"""
    global _KEYWORD_PATTERNS
    if len(_KEYWORD_PATTERNS) > 0:
        return

    for keyword in BILL_RELATED_KEYWORDS:
        keyword_lower = keyword.lower()

        # 特殊文字を含むキーワード（B/L, bill of lading など）は単純な部分一致なのでパターン不要
        if "/" in keyword_lower or " " in keyword_lower:
            _KEYWORD_PATTERNS.append((keyword, keyword_lower, None))
        # 短い日本語キーワード（2-3文字）は単語境界を考慮したパターン
        elif len(keyword_lower) <= 3 and any("\u4e00" <= c <= "\u9fff" for c in keyword_lower):
            pattern = re.compile(
                r"(?<![\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF])"
                + re.escape(keyword_lower)
                + r"(?![\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF])"
            )
            _KEYWORD_PATTERNS.append((keyword, keyword_lower, pattern))
        # 短い英数字キーワードは単語境界を考慮したパターン
        elif len(keyword_lower) <= 3:
            pattern = re.compile(
                r"(?<![a-zA-Z0-9])" + re.escape(keyword_lower) + r"(?![a-zA-Z0-9])"
            )
            _KEYWORD_PATTERNS.append((keyword, keyword_lower, pattern))
        # 長いキーワードは通常の部分一致なのでパターン不要
        else:
            _KEYWORD_PATTERNS.append((keyword, keyword_lower, None))


# モジュールロード時にパターンを構築
_build_keyword_patterns()

# 無関係と判断されやすいパターン（これらが主な内容の場合は低スコア）
# 事前にコンパイルしてパフォーマンスを向上
IRRELEVANT_PATTERNS = [
    # 単純な挨拶や相槌のみ
    re.compile(r"^(はい|いいえ|うん|ええ|そう|なるほど|わかりました|了解|OK)$"),
    re.compile(r"^(あ+|え+|お+|う+)$"),  # 「ああああ」など
    # 明確に知らない・わからないという発言
    re.compile(r"^(知らない|分からない|わからない|聞いたことがない|初めて聞)([。．.!！?？\s]*)$"),
]


def calculate_relevance_score(message_content: str) -> float:
    """メッセージ内容から法案・業務関連度スコアを計算する。

    Args:
        message_content: メッセージ本文

    Returns:
        関連度スコア (0.0～1.0)
        - 1.0に近いほど関連度が高い
        - 0.0に近いほど無関係
    """
    if not message_content or not message_content.strip():
        return 0.0

    content = message_content.strip()
    content_lower = content.lower()

    # パターン1: 明確に無関係なパターンに該当する場合は低スコア
    for pattern in IRRELEVANT_PATTERNS:
        if pattern.search(content):
            logger.debug(
                "無関係パターンに該当: pattern={}, content={}",
                pattern.pattern,
                content[:50],
            )
            return 0.1

    # パターン2: 極端に短いメッセージは低スコア（ただし完全に0ではない）
    if len(content) < 5:
        return 0.2

    # パターン3: キーワードマッチングによるスコアリング（事前コンパイルされたパターンを使用）
    matched_keywords: list[str] = []
    for keyword, keyword_lower, kw_pattern in _KEYWORD_PATTERNS:
        if kw_pattern is None:
            # パターンなし = 単純な部分一致
            if keyword_lower in content_lower:
                matched_keywords.append(keyword)
        else:
            # 事前コンパイルされたパターンでマッチング
            if kw_pattern.search(content_lower):
                matched_keywords.append(keyword)

    # マッチしたキーワード数に応じてスコアを計算
    # 0個: 0.25, 1個: 0.4, 2個: 0.6, 3個以上: 0.8～1.0
    keyword_count = len(matched_keywords)
    if keyword_count == 0:
        base_score = 0.1
    elif keyword_count == 1:
        base_score = 0.4
    elif keyword_count == 2:
        base_score = 0.6
    else:
        # 3個以上は0.8から始まり、多いほど1.0に近づく
        base_score = min(0.8 + (keyword_count - 3) * 0.05, 1.0)

    # パターン4: メッセージの長さによる補正（具体的な内容ほど高スコア）
    # 100文字以上の場合は+0.1、200文字以上の場合は+0.2（最大1.0）
    length_bonus = 0.0
    if len(content) >= 100:
        length_bonus = 0.1
    if len(content) >= 200:
        length_bonus = 0.2

    final_score = min(base_score + length_bonus, 1.0)

    if matched_keywords:
        logger.debug(
            "関連度スコア計算: score={:.2f}, matched_keywords={}, content={}",
            final_score,
            matched_keywords[:3],  # 最初の3つだけログ出力
            content[:50],
        )

    return final_score


def filter_messages_by_relevance(
    messages_df: "pd.DataFrame",
    threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    content_col: str = "content",
) -> "pd.DataFrame":
    """メッセージDataFrameから関連度の低いメッセージを除外する。

    Args:
        messages_df: メッセージを含むDataFrame
        threshold: 関連度の閾値（この値以下のメッセージは除外される）
        content_col: メッセージ本文の列名

    Returns:
        フィルタリング後のDataFrame
    """
    if content_col not in messages_df.columns:
        logger.warning(
            "メッセージ列 '{}' が見つかりません。フィルタリングをスキップします。",
            content_col,
        )
        return messages_df

    # 各メッセージの関連度スコアを計算
    relevance_scores = messages_df[content_col].apply(calculate_relevance_score)

    # 閾値以上のメッセージのみを残す
    filtered_df = messages_df[relevance_scores > threshold].copy()

    # ログ出力
    total_messages = len(messages_df)
    filtered_messages = len(filtered_df)
    excluded_messages = total_messages - filtered_messages

    logger.info(
        "メッセージフィルタリング完了: 全{}件 → {}件に削減 (除外: {}件, {}%)",
        total_messages,
        filtered_messages,
        excluded_messages,
        round(excluded_messages / total_messages * 100, 1) if total_messages > 0 else 0,
    )

    # 除外されたメッセージの詳細をデバッグログに出力
    if excluded_messages > 0:
        excluded_df = messages_df[relevance_scores <= threshold].copy()
        # 除外されたメッセージのスコアも一緒に保存
        excluded_scores = relevance_scores[relevance_scores <= threshold]
        logger.debug("除外されたメッセージ数: {}", excluded_messages)

        # 最初の数件を詳細ログ出力（デバッグ用）
        sample_size = min(10, excluded_messages)
        for idx in range(sample_size):
            row = excluded_df.iloc[idx]
            content = str(row[content_col])[:100]  # 最初の100文字
            score = excluded_scores.iloc[idx]
            logger.debug(
                "除外メッセージ例 {}/{}: score={:.2f}, content={}",
                idx + 1,
                sample_size,
                score,
                content,
            )

    return filtered_df
