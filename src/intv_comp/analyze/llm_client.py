"""
OpenAI LLM呼び出し周りを切り出したクライアントモジュール。
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from openai import APIConnectionError, APIStatusError, AuthenticationError

from intv_comp.logger import logger

# .envファイルを読み込んでAPIキーやモデル名を環境変数に反映
load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")


def _require_api_key() -> str:
    """環境変数に設定されたAPIキーを取得する。存在しない場合は例外を発生させる。"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "環境変数 OPENAI_API_KEY が設定されていません。APIキーを設定してから再実行してください。"
        )
    return api_key


class LLMClient:
    """OpenAIチャットモデルを簡単に呼び出すための軽量クライアント。"""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        _require_api_key()
        self.model = model
        self.client = OpenAI()

    def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """system/userプロンプトを渡してモデルの応答文字列を返す。"""
        try:
            logger.info(
                "OpenAI API呼び出し開始: model={}, temperature={}, max_tokens={}",
                self.model,
                temperature,
                max_tokens,
            )
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            logger.info(
                "OpenAI API呼び出し完了: model={}, temperature={}, max_tokens={}",
                self.model,
                temperature,
                max_tokens,
            )
        except AuthenticationError as exc:
            logger.error("OpenAIの認証に失敗しました。APIキーを確認してください。", exc_info=True)
            raise RuntimeError("OpenAIの認証に失敗しました。APIキーを確認してください。") from exc
        except APIStatusError as exc:
            logger.error(
                "OpenAI APIリクエストに失敗しました。status={} message={}",
                exc.status_code,
                exc.message,
                exc_info=True,
            )
            raise RuntimeError(
                f"OpenAI APIリクエストに失敗しました。status={exc.status_code} message={exc.message}"
            ) from exc
        except APIConnectionError as exc:
            logger.error("OpenAI APIに接続できませんでした。ネットワークを確認してください。", exc_info=True)
            raise RuntimeError("OpenAI APIに接続できませんでした。ネットワークを確認してください。") from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("OpenAI API呼び出し中に予期しないエラーが発生しました。", exc_info=True)
            raise RuntimeError("OpenAI API呼び出し中に予期しないエラーが発生しました。") from exc

        choice = response.choices[0]
        return choice.message.content or ""
