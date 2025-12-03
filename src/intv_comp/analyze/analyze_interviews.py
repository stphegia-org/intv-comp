"""
AIインタビューログのCSVを読み込み、セッション単位でLLMに分析を依頼し、Markdownレポートを出力するスクリプト。

実際の列名やモデル名は冒頭の定数にまとめているので、必要に応じて書き換えてください。
"""
from __future__ import annotations

import argparse
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd
from dotenv import load_dotenv

from intv_comp.analyze.llm_client import DEFAULT_MODEL, LLMClient

# .envファイルを読み込んで環境変数を反映
load_dotenv()

# ===== CSV列名の定義（実際のデータに合わせて修正してください） =====
SESSION_ID_COL = "session_id"  # メッセージCSVのセッションID列名
MESSAGE_CONTENT_COL = "content"  # メッセージCSVのメッセージ本文列名
ROLE_COL = "role"  # メッセージCSVの話者ロール列名
TIMESTAMP_COL = "timestamp"  # メッセージCSVのタイムスタンプ列名


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
        ids = sessions_df[SESSION_ID_COL].dropna().astype(str).tolist()
        return ids
    # セッション情報がない場合はメッセージ側のユニーク値で代替
    ids = messages_df[SESSION_ID_COL].dropna().astype(str).unique().tolist()
    return ids


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


def build_session_prompt(session_id: str, transcript: str) -> str:
    """セッション単位の分析を行うためのユーザープロンプトを生成する。"""
    prompt = f"""
以下はインタビューセッションID: {session_id} の全文ログです。テキストを読み込み、以下をMarkdownでまとめてください。

- インタビュー対象者の主な主張・懸念点
- 法整備の観点で重要になりそうな論点
- インタビュアー／対象者が暗黙に前提としているルールや慣行
- 現行法や制度では拾いきれていない可能性があるポイント
- 追加で調査すべき事項や確認が必要な前提

出力は「## セッション {session_id}」配下に箇条書きを含む読みやすいMarkdownで記載してください。

---
{transcript}
"""
    return prompt


def build_cross_session_prompt(per_session_summaries: List[str]) -> str:
    """複数セッションを俯瞰して共通論点や示唆を抽出するプロンプトを生成する。"""
    joined = "\n\n".join(per_session_summaries)
    prompt = f"""
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
{joined}
"""
    return prompt


def extract_tagged_section(text: str, tag: str) -> str:
    """[tag]...[/tag] の区間を抽出するヘルパー。"""
    pattern = re.compile(rf"\[{tag}\](.*?)\[/{tag}\]", re.DOTALL)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return ""


def render_report(
    overall_summary: str,
    overlooked_points: str,
    suggestions: str,
    per_session_sections: List[str],
) -> str:
    """Markdownレポート全文を生成する。"""
    session_block = "\n\n".join(per_session_sections)
    return f"""
# AIインタビューログ分析レポート

## 1. 全体サマリー
{overall_summary}

## 2. セッション別の主な論点
{session_block}

## 3. 法整備の観点で見落とされがちなポイント
{overlooked_points}

## 4. 改善提案・示唆
{suggestions}
"""


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(description="AIインタビューログを分析してMarkdownレポートを生成します。")
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
    return parser.parse_args()


def main() -> None:
    """メイン関数。"""
    args = parse_arguments()
    try:
        messages_df = load_csv(args.messages_file)
        sessions_df = load_csv(args.sessions_file)

        validate_required_columns(
            messages_df,
            [SESSION_ID_COL, MESSAGE_CONTENT_COL, ROLE_COL, TIMESTAMP_COL],
            "メッセージCSV",
        )

        session_order = get_session_order(sessions_df, messages_df)
        selected_ids = select_session_ids(session_order, args.limit_sessions, args.sample)
        grouped_messages = group_messages_by_session(messages_df)

        if not selected_ids:
            raise RuntimeError("分析対象のセッションが見つかりませんでした。CSVの内容を確認してください。")

        llm = LLMClient(model=args.model)

        per_session_results: List[str] = []
        for session_id in selected_ids:
            session_df = grouped_messages.get(str(session_id))
            if session_df is None:
                continue
            transcript = build_session_transcript(session_df)
            user_prompt = build_session_prompt(str(session_id), transcript)
            session_analysis = llm.chat_completion(
                system_prompt=(
                    "あなたはリーガルテック領域の調査アナリストです。"
                    "インタビュー会話から立法・制度設計に影響する論点を掘り起こしてください。"
                ),
                user_prompt=user_prompt,
            )
            per_session_results.append(session_analysis)

        cross_prompt = build_cross_session_prompt(per_session_results)
        cross_response = llm.chat_completion(
            system_prompt=(
                "あなたは政策立案担当者向けに論点を整理する専門家です。"
                "複数のインタビュー要約をもとに、制度の隙間や暗黙の前提を明確化してください。"
            ),
            user_prompt=cross_prompt,
        )

        overall_summary = extract_tagged_section(cross_response, "overall_summary")
        overlooked_points = extract_tagged_section(cross_response, "overlooked_points")
        suggestions = extract_tagged_section(cross_response, "suggestions")

        report = render_report(
            overall_summary=overall_summary,
            overlooked_points=overlooked_points,
            suggestions=suggestions,
            per_session_sections=per_session_results,
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"レポートを出力しました: {args.output}")
    except FileNotFoundError as exc:
        print(str(exc))
        raise RuntimeError(str(exc)) from exc
    except RuntimeError as exc:
        print(str(exc))
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        print("予期しないエラーが発生しました。入力データやAPI設定を確認してください。")
        print(str(exc))
        raise RuntimeError(str(exc)) from exc


if __name__ == "__main__":
    main()
