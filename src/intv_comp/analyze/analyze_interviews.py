"""
AIインタビューログのCSVを読み込み、全メッセージをグローバル分析し、Markdownレポートを出力するスクリプト。

実際の列名やモデル名は冒頭の定数にまとめているので、必要に応じて書き換えてください。
"""

from __future__ import annotations

import argparse
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Sequence
from urllib.parse import quote

import pandas as pd
from dotenv import load_dotenv

try:
    import tiktoken

    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

from intv_comp.analyze.llm_client import DEFAULT_MODEL, LLMClient
from intv_comp.analyze.reference_loader import load_reference_materials
from intv_comp.logger import logger, setup_logger

# .envファイルを読み込んで環境変数を反映
load_dotenv()

# ===== CSV列名の定義（実際のデータに合わせて修正してください） =====
SESSION_ID_COL = "session_id"  # メッセージCSVのセッションID列名
MESSAGE_CONTENT_COL = "content"  # メッセージCSVのメッセージ本文列名
ROLE_COL = "role"  # メッセージCSVの話者ロール列名
TIMESTAMP_COL = "timestamp"  # メッセージCSVのタイムスタンプ列名

# チャンク分割の設定
DEFAULT_MAX_TOKENS_PER_CHUNK = int(os.getenv("MAX_TOKENS_PER_CHUNK", "8000"))

# 全体統合プロンプトに含めるテキストのトークン上限（TPM 制限に収まるようにマージンを取る）
DEFAULT_MAX_TOKENS_FOR_GLOBAL_PROMPT = int(os.getenv("MAX_TOKENS_FOR_GLOBAL_PROMPT", "24000"))

# チャンクサマリ圧縮の設定
DEFAULT_COMPRESSION_MAX_ROUNDS = 2  # 圧縮ラウンドの上限
DEFAULT_COMPRESSION_BATCH_SIZE = 10  # 1回の圧縮で処理するサマリ数


def _get_env_var(env_var: str) -> str:
    """環境変数を取得する。存在しない場合は例外を発生させる。"""
    path = os.getenv(env_var)
    if not path or not path.strip():
        raise RuntimeError(
            f"環境変数 {env_var} が設定されていません。.envファイルに設定してから再実行してください。"
        )
    return path.strip()


# ===== デフォルトパス設定 =====
DEFAULT_MESSAGES_PATH = Path(_get_env_var("MESSAGES_CSV_PATH"))
DEFAULT_SESSIONS_PATH = Path(_get_env_var("SESSIONS_CSV_PATH"))
DEFAULT_OUTPUT_PATH = Path(_get_env_var("REPORT_OUTPUT_PATH"))


def _get_env_var_optional(env_var: str, default: str) -> str:
    """環境変数を取得する。存在しない場合はデフォルト値を返す。"""
    value = os.getenv(env_var)
    if not value or not value.strip():
        return default
    return value.strip()


# デフォルトの追加資料ディレクトリ
DEFAULT_REFERENCES_DIR = Path(_get_env_var_optional("REFERENCES_DIR", "data/references"))


def load_csv(path: Path) -> pd.DataFrame:
    """CSVを読み込み、存在しない場合はわかりやすいエラーを返す。"""
    if not path.exists():
        raise FileNotFoundError(f"CSVファイルが見つかりません: {path}")
    return pd.read_csv(path)


def validate_required_columns(df: pd.DataFrame, required: Sequence[str], label: str) -> None:
    """データフレームに必要な列が存在するかを検証する。"""
    missing = [col for col in required if col not in df.columns]
    if missing:
        missing_cols = ", ".join(missing)
        raise RuntimeError(
            f"{label} に必要な列が不足しています: {missing_cols}. "
            "列名定数を実データに合わせて修正してください。"
        )


def get_session_order(sessions_df: pd.DataFrame, messages_df: pd.DataFrame) -> List[str]:
    """セッションIDのリストを取得する。sessions_dfになければmessages_dfからuniqueを取得。"""
    if SESSION_ID_COL in sessions_df.columns:
        ids: List[str] = sessions_df[SESSION_ID_COL].dropna().astype(str).tolist()
        return ids
    # セッション情報がない場合はメッセージ側のユニーク値で代替
    unique_ids: List[str] = messages_df[SESSION_ID_COL].dropna().astype(str).unique().tolist()
    return unique_ids


def select_session_ids(
    session_ids: Sequence[str],
    limit_sessions: int | None,
    sample: bool = False,
) -> List[str]:
    """セッションIDを制限・サンプリングして返す。"""
    ids = list(session_ids)
    if sample and limit_sessions:
        ids = random.sample(ids, k=min(limit_sessions, len(ids)))
    elif limit_sessions:
        ids = ids[:limit_sessions]
    return ids


def group_messages_by_session(messages_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """セッションIDごとにメッセージをソート済みDataFrameとしてまとめる。"""
    grouped: Dict[str, pd.DataFrame] = {}
    for session_id, group in messages_df.groupby(SESSION_ID_COL):
        sorted_group = group.sort_values(TIMESTAMP_COL)
        grouped[str(session_id)] = sorted_group
    return grouped


def build_session_transcript(session_df: pd.DataFrame) -> str:
    """1セッションのメッセージをタイムスタンプ順で結合したテキストを生成する。"""
    lines: List[str] = []
    for _, row in session_df.iterrows():
        timestamp = row.get(TIMESTAMP_COL, "")
        role = row.get(ROLE_COL, "")
        message = row.get(MESSAGE_CONTENT_COL, "")
        lines.append(f"[{timestamp}] {role}: {message}")
    return "\n".join(lines)


def build_global_transcript_df(messages_df: pd.DataFrame) -> pd.DataFrame:
    """全メッセージをタイムスタンプ順に並べたDataFrameを返す。

    Args:
        messages_df: メッセージを含むDataFrame

    Returns:
        タイムスタンプでソートされたDataFrame
    """
    return messages_df.sort_values(TIMESTAMP_COL).reset_index(drop=True)


def _estimate_token_count(text: str, model: str = DEFAULT_MODEL) -> int:
    """テキストのトークン数を見積もる。

    Args:
        text: トークン数を見積もるテキスト
        model: 使用するモデル名（tiktokenのエンコーディング選択に使用）

    Returns:
        推定トークン数
    """
    if HAS_TIKTOKEN:
        try:
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                logger.warning(
                    "モデル '%s' のエンコーディングが取得できなかったため "
                    "'cl100k_base' を使用します。",
                    model,
                )
                encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except (KeyError, ValueError) as exc:
            logger.warning(
                "tiktoken によるトークン見積もりに失敗したため、概算値を使用します: %s",
                exc,
            )
            return len(text) // 4
    else:
        # tiktokenが使えない場合は文字数ベースの概算
        return len(text) // 4


def chunk_messages_for_llm(
    sorted_messages_df: pd.DataFrame,
    max_tokens_per_chunk: int,
    model: str = DEFAULT_MODEL,
) -> List[str]:
    """タイムスタンプ順のメッセージをトークン上限を考慮してチャンクに分割する。

    Args:
        sorted_messages_df: タイムスタンプ順にソートされたメッセージDataFrame
        max_tokens_per_chunk: 1チャンクあたりの最大トークン数
        model: 使用するモデル名（トークン推定に使用）

    Returns:
        チャンクごとのテキストリスト
    """
    chunks: List[str] = []
    current_chunk_text = ""

    for _, row in sorted_messages_df.iterrows():
        timestamp = row.get(TIMESTAMP_COL, "")
        role = row.get(ROLE_COL, "")
        message = row.get(MESSAGE_CONTENT_COL, "")
        line = f"[{timestamp}] {role}: {message}"

        # 単一メッセージのトークン数を計算（効率化のため1回のみ）
        line_tokens = _estimate_token_count(line, model)

        # 単一メッセージがmax_tokens_per_chunkを超える場合の処理
        if line_tokens > max_tokens_per_chunk:
            # 現在のチャンクがあれば確定
            if current_chunk_text:
                chunks.append(current_chunk_text)
            # 大きなメッセージを単独で1チャンクとして追加
            chunks.append(line)
            current_chunk_text = ""
            logger.warning(
                "単一メッセージがmax_tokens_per_chunk ({}) を超えています。"
                "このメッセージは単独で1チャンクとして扱われます。",
                max_tokens_per_chunk,
            )
            continue

        # 通常のチャンク分割ロジック
        if current_chunk_text:
            current_tokens = _estimate_token_count(current_chunk_text, model)
            if current_tokens + line_tokens > max_tokens_per_chunk:
                # 現在のチャンクを確定して次のチャンクへ
                chunks.append(current_chunk_text)
                current_chunk_text = line
            else:
                # 現在のチャンクに追加
                current_chunk_text = current_chunk_text + "\n" + line
        else:
            # 最初のメッセージ
            current_chunk_text = line

    # 最後のチャンクを追加
    if current_chunk_text:
        chunks.append(current_chunk_text)

    logger.info("全メッセージを {} 個のチャンクに分割しました", len(chunks))
    return chunks


def compress_chunk_summaries(
    chunk_summaries: List[str],
    llm: LLMClient,
    model: str,
    max_tokens_for_global_prompt: int = DEFAULT_MAX_TOKENS_FOR_GLOBAL_PROMPT,
) -> List[str]:
    """全体統合プロンプトに渡すチャンクサマリを階層的に圧縮する。

    - chunk_summaries 全体をそのまま連結したときの推定トークン数が
      max_tokens_for_global_prompt を超える場合、バッチごとに LLM に再要約させて
      要約リストを作り直す。
    - バッチ要約を 1〜2 ラウンド行い、十分に小さくなったところで終了する。
    - 情報を完全には保持できないが、「全体像を掴む」という用途には
      影響が少ないよう、要点を残した圧縮を行う。
    """
    if not chunk_summaries:
        return chunk_summaries

    # まず現在の合計トークン数を概算
    joined = "\n\n".join(chunk_summaries)
    total_tokens = _estimate_token_count(joined, model=model)
    if total_tokens <= max_tokens_for_global_prompt:
        # そもそも十分小さい場合はそのまま返す
        logger.info(
            "全体統合プロンプト用チャンクサマリは推定 {} トークンのため圧縮不要です",
            total_tokens,
        )
        return chunk_summaries

    logger.warning(
        "全体統合プロンプト用チャンクサマリが大きすぎます（推定: {} トークン）。"
        " 階層的に圧縮を行います。",
        total_tokens,
    )

    current = chunk_summaries
    max_rounds = DEFAULT_COMPRESSION_MAX_ROUNDS
    batch_size = DEFAULT_COMPRESSION_BATCH_SIZE

    for round_index in range(max_rounds):
        if len(current) == 1:
            # これ以上は圧縮しようがないので終了
            break

        next_level: List[str] = []
        for i in range(0, len(current), batch_size):
            batch = current[i : i + batch_size]
            if not batch:
                continue

            batch_text = "\n\n---\n\n".join(batch)
            batch_prompt = f"""以下はインタビューログを分割して得られた部分分析結果の一部です。
複数のサマリを統合し、**重複を減らしつつ重要な論点を残す形で**日本語の箇条書きに要約してください。

- 法整備・制度設計の観点で重要なポイント
- 暗黙の前提や制度の隙間
- 追加で検討すべき示唆

出力は 1 つのまとまったサマリのみとし、できるだけ簡潔にしてください。

---
## 統合対象サマリ

{batch_text}
"""

            summary = llm.chat_completion(
                system_prompt=(
                    "あなたはリーガルテック領域の調査アナリストです。"
                    "複数の部分サマリから重複を削り、重要な論点だけを残して要約してください。"
                ),
                user_prompt=batch_prompt,
            )
            next_level.append(summary)

        current = next_level

        # 圧縮後のサイズを確認
        joined = "\n\n".join(current)
        total_tokens = _estimate_token_count(joined, model=model)
        logger.info(
            "チャンクサマリ圧縮ラウンド {} 終了: 要素数={}, 推定トークン数={}",
            round_index + 1,
            len(current),
            total_tokens,
        )
        if total_tokens <= max_tokens_for_global_prompt:
            break

    return current


def build_session_prompt(session_id: str, transcript: str, reference_materials: str = "") -> str:
    """セッション単位の分析を行うためのユーザープロンプトを生成する。"""
    base_prompt = f"""
以下はインタビューセッションID: {session_id} の全文ログです。テキストを読み込み、以下をMarkdownでまとめてください。

- インタビュー対象者の主な主張・懸念点
- 法整備の観点で重要になりそうな論点
- インタビュアー／対象者が暗黙に前提としているルールや慣行
- 現行法や制度では拾いきれていない可能性があるポイント
- 追加で調査すべき事項や確認が必要な前提

出力は「## セッション {session_id}」配下に箇条書きを含む読みやすいMarkdownで記載してください。

---
## インタビューログ

{transcript}
"""

    if reference_materials:
        base_prompt += f"""
---
## 参考資料

以下の追加資料も分析の参考にしてください：

{reference_materials}
"""

    return base_prompt


def build_chunk_analysis_prompt(
    chunk_index: int,
    total_chunks: int,
    chunk_text: str,
    reference_materials: str = "",
) -> str:
    """チャンク単位の部分分析を行うためのユーザープロンプトを生成する。

    Args:
        chunk_index: 現在のチャンクのインデックス（0始まり）
        total_chunks: 全チャンク数
        chunk_text: チャンクのテキスト
        reference_materials: 参考資料（オプション）

    Returns:
        チャンク分析用のプロンプト文字列
    """
    base_prompt = f"""
以下は全インタビューログを時間順に分割した一部分です（チャンク {chunk_index + 1}/{total_chunks}）。
このチャンクから読み取れる重要な論点や示唆を抽出してください。

最終的な統合レポートは別のステップで作成されるため、この段階では「部分的な発見」を以下の観点で箇条書きにしてください。
重要と思うポイントを漏らさず挙げてください。

**分析観点：**
- インタビュー対象者の主な主張・懸念点
- 法整備の観点で重要になりそうな論点
- インタビュアー／対象者が暗黙に前提としているルールや慣行
- 現行法や制度では拾いきれていない可能性があるポイント
- 追加で調査すべき事項や確認が必要な前提

---
## インタビューログ（チャンク {chunk_index + 1}/{total_chunks}）

{chunk_text}
"""

    # TODO: 参考資料は将来的にサマリに差し替える可能性があるため、現時点では含めない
    # 必要に応じて以下の実装を追加可能

    return base_prompt


def build_cross_session_prompt(
    per_session_summaries: List[str],
    reference_materials: str = "",
) -> str:
    """複数セッションを俯瞰して共通論点や示唆を抽出するプロンプトを生成する。"""
    joined = "\n\n".join(per_session_summaries)
    base_prompt = f"""
以下は各セッションの分析結果です。全体を俯瞰し、共通するパターンや見落とされがちな論点を抽出してください。
結果は以下の3セクションを日本語Markdownで生成してください。

[overall_summary]
- 全体サマリー（複数セッションを通じた主要な洞察）
[/overall_summary]
[overlooked_points]
- 法整備の観点で見落とされがちなポイント（暗黙の前提や制度の隙間を含む）
[/overlooked_points]
[suggestions]
- 改善提案・追加で検討すべき示唆
[/suggestions]

---
## セッション分析結果

{joined}
"""

    if reference_materials:
        base_prompt += f"""
---
## 参考資料

以下の追加資料も分析の参考にしてください：

{reference_materials}
"""

    return base_prompt


def build_global_summary_prompt(
    chunk_summaries: List[str],
    reference_materials: str = "",
) -> str:
    """チャンク分析結果から全体レポートを作成するプロンプトを生成する。

    Args:
        chunk_summaries: 各チャンクの分析結果リスト
        reference_materials: 参考資料（オプション）

    Returns:
        全体統合用のプロンプト文字列
    """
    joined = "\n\n---\n\n".join(
        f"### チャンク {i + 1} の分析結果\n\n{summary}" for i, summary in enumerate(chunk_summaries)
    )

    base_prompt = f"""
以下は全インタビューログを複数のチャンクに分けて分析した結果です。
これらの部分分析を統合し、全体を俯瞰した上で、共通するパターンや見落とされがちな論点を抽出してください。

結果は以下の3セクションを日本語Markdownで生成してください：

[overall_summary]
- 全体サマリー（全てのインタビューを通じた主要な洞察）
[/overall_summary]
[overlooked_points]
- 法整備の観点で見落とされがちなポイント（暗黙の前提や制度の隙間を含む）
[/overlooked_points]
[suggestions]
- 改善提案・追加で検討すべき示唆
[/suggestions]

---
## チャンク分析結果

{joined}
"""

    # 参考資料のトークン数をチェックして、大きすぎる場合は含めない
    if reference_materials:
        ref_tokens = _estimate_token_count(reference_materials)
        if ref_tokens > 10000:
            logger.warning(
                f"参考資料のトークン数が大きいため（推定: {ref_tokens:,}トークン）、"
                "全体統合プロンプトには含めません。"
            )
        else:
            base_prompt += f"""
---
## 参考資料

以下の追加資料も分析の参考にしてください：

{reference_materials}
"""

    return base_prompt


def extract_tagged_section(text: str, tag: str) -> str:
    """[tag]...[/tag] の区間を抽出するヘルパー。"""
    pattern = re.compile(rf"\[{tag}\](.*?)\[/{tag}\]", re.DOTALL)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return ""


def build_session_urls_section(session_ids: List[str]) -> str:
    """セッションURLのMarkdownセクションを生成する。

    Args:
        session_ids: セッションIDのリスト

    Returns:
        セッションURLのMarkdownセクション文字列
    """
    if not session_ids:
        return ""

    lines = ["## 0. 分析対象セッション一覧", ""]
    for session_id in session_ids:
        url = f"https://depth-interview-ai.vercel.app/report/{quote(session_id, safe='')}"
        lines.append(f"- **セッションID**: `{session_id}`")
        lines.append(f"  - 元インタビューセッション: [depth-interview-aiで開く]({url})")
        lines.append("")

    return "\n".join(lines)


def render_report(
    overall_summary: str,
    overlooked_points: str,
    suggestions: str,
    session_ids: List[str] | None = None,
) -> str:
    """Markdownレポート全文を生成する。

    Args:
        overall_summary: 全体サマリー
        overlooked_points: 見落とされがちなポイント
        suggestions: 改善提案・示唆
        session_ids: セッションIDのリスト（オプション）

    Returns:
        レポートのMarkdown文字列
    """
    session_section = ""
    if session_ids:
        session_section = build_session_urls_section(session_ids) + "\n\n"

    return f"""
# AIインタビューログ分析レポート

{session_section}## 1. 全体サマリー
{overall_summary}

## 2. 法整備の観点で見落とされがちなポイント
{overlooked_points}

## 3. 改善提案・示唆
{suggestions}
"""


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="AIインタビューログを分析してMarkdownレポートを生成します。"
    )
    parser.add_argument(
        "--messages-file",
        type=Path,
        default=DEFAULT_MESSAGES_PATH,
        help="インタビューのメッセージCSVパス",
    )
    parser.add_argument(
        "--sessions-file",
        type=Path,
        default=DEFAULT_SESSIONS_PATH,
        help="セッションメタデータのCSVパス",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="生成するMarkdownレポートの出力先",
    )
    parser.add_argument(
        "--limit-sessions",
        type=int,
        default=None,
        help="分析対象とするセッション数の上限",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="セッションをランダムサンプリングして分析する",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help="使用するOpenAIモデル名",
    )
    parser.add_argument(
        "--references-dir",
        type=Path,
        default=DEFAULT_REFERENCES_DIR,
        help="追加資料（参考資料）が格納されているディレクトリのパス",
    )
    return parser.parse_args()


def main() -> None:
    """メイン関数。"""
    # ロガーの設定
    setup_logger()

    args = parse_arguments()
    try:
        # 参照ディレクトリのパス検証
        if args.references_dir.is_absolute():
            logger.warning("絶対パスが指定されました。相対パスの使用を推奨します。")

        messages_df = load_csv(args.messages_file)
        # セッション情報は将来的にフィルタ条件などに使用する可能性があるため読み込む
        # _sessions_df = load_csv(args.sessions_file)

        validate_required_columns(
            messages_df,
            [SESSION_ID_COL, MESSAGE_CONTENT_COL, ROLE_COL, TIMESTAMP_COL],
            "メッセージCSV",
        )

        # 追加資料を読み込む
        reference_materials = load_reference_materials(args.references_dir)

        # トークン使用量の警告
        if reference_materials:
            estimated_tokens = _estimate_token_count(reference_materials, args.model)
            if estimated_tokens > 10000:
                logger.warning(
                    "追加資料のトークン数が大きい可能性があります（推定: {:,}トークン）。",
                    estimated_tokens,
                )

        # 全メッセージを時間順に並べる
        logger.info("全メッセージを時間順に並べています...")
        sorted_messages_df = build_global_transcript_df(messages_df)
        logger.info("全 {} 件のメッセージを処理対象としました", len(sorted_messages_df))

        # メッセージをチャンクに分割
        logger.info("メッセージをチャンクに分割しています...")
        chunks = chunk_messages_for_llm(
            sorted_messages_df,
            max_tokens_per_chunk=DEFAULT_MAX_TOKENS_PER_CHUNK,
            model=args.model,
        )

        if not chunks:
            raise RuntimeError(
                "分析対象のメッセージが見つかりませんでした。CSVの内容を確認してください。"
            )

        llm = LLMClient(model=args.model)

        # 各チャンクを分析
        chunk_summaries: List[str] = []
        for i, chunk_text in enumerate(chunks):
            logger.info("チャンク {}/{} を分析中...", i + 1, len(chunks))
            chunk_prompt = build_chunk_analysis_prompt(
                chunk_index=i,
                total_chunks=len(chunks),
                chunk_text=chunk_text,
                reference_materials="",  # チャンク分析では参考資料を含めない
            )
            chunk_analysis = llm.chat_completion(
                system_prompt=(
                    "あなたはリーガルテック領域の調査アナリストです。"
                    "インタビュー会話から立法・制度設計に影響する論点を掘り起こしてください。"
                ),
                user_prompt=chunk_prompt,
            )
            chunk_summaries.append(chunk_analysis)

        # 全体統合プロンプト用にチャンクサマリを圧縮
        logger.info("全体統合プロンプト用にチャンクサマリを圧縮しています...")
        compressed_chunk_summaries = compress_chunk_summaries(
            chunk_summaries=chunk_summaries,
            llm=llm,
            model=args.model,
            max_tokens_for_global_prompt=DEFAULT_MAX_TOKENS_FOR_GLOBAL_PROMPT,
        )

        # 圧縮後のサマリから全体統合レポートを生成
        logger.info("チャンク分析結果を統合して全体レポートを生成中...")
        global_prompt = build_global_summary_prompt(compressed_chunk_summaries, reference_materials)
        global_response = llm.chat_completion(
            system_prompt=(
                "あなたは政策立案担当者向けに論点を整理する専門家です。"
                "複数のチャンク分析をもとに、制度の隙間や暗黙の前提を明確化してください。"
            ),
            user_prompt=global_prompt,
        )

        overall_summary = extract_tagged_section(global_response, "overall_summary")
        overlooked_points = extract_tagged_section(global_response, "overlooked_points")
        suggestions = extract_tagged_section(global_response, "suggestions")

        # セッションIDのリストを取得
        unique_session_ids = sorted(
            messages_df[SESSION_ID_COL].dropna().astype(str).unique()
        )
        logger.info("分析対象のセッション数: {}", len(unique_session_ids))

        report = render_report(
            overall_summary=overall_summary,
            overlooked_points=overlooked_points,
            suggestions=suggestions,
            session_ids=unique_session_ids,
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        logger.info(f"レポートを出力しました: {args.output}")
    except FileNotFoundError as exc:
        logger.error(str(exc))
        raise RuntimeError(str(exc)) from exc
    except RuntimeError as exc:
        logger.error(str(exc))
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        logger.error("予期しないエラーが発生しました。入力データやAPI設定を確認してください。")
        logger.error(str(exc))
        raise RuntimeError(str(exc)) from exc


if __name__ == "__main__":
    main()
