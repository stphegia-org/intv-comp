# メッセージフィルタリング機能

## 概要

このモジュールは、インタビューCSVから法案・対象業務と無関係な発言を除外し、LLMへ送信するチャンクをフィルタリングする機能を提供します。

## 目的

インタビューCSVには、以下のような無関係な発言が多数含まれています：

- 法案の内容を知らない参加者の意見
- 法案化対象業務を理解していない発言
- 法案や業務と無関係な雑談・ノイズ

これらをそのままチャンクとしてLLMに送信すると、分析精度が大きく低下します。
本機能により、法案または法案化対象業務に関連する発言だけを抽出し、関係ない発言をLLMに送信しないようにします。

## 実装概要

### 関連度スコアリング (`calculate_relevance_score`)

各メッセージの内容を分析し、0.0～1.0の関連度スコアを計算します。

#### スコアリング基準

1. **無関係パターンの検出** (スコア: 0.1)
   - 単純な挨拶や相槌のみ（「はい」「ええ」「なるほど」など）
   - 「ああああ」などの意味のない発言
   - 明確に知らない・わからないという発言

2. **メッセージの長さ** (スコア: 0.2)
   - 5文字未満の極端に短いメッセージ

3. **キーワードマッチング** (スコア: 0.25～1.0)
   - 法案・制度関連キーワード（法案、法律、制度、規制、政策など）
   - 船荷証券・貿易関連キーワード（船荷証券、B/L、電子化、貿易、輸出入など）
   - 業務・実務関連キーワード（実務、業務、手続き、システムなど）
   - マッチ数に応じてスコアが上昇

4. **長文ボーナス** (+0.1～0.2)
   - 100文字以上: +0.1
   - 200文字以上: +0.2

### フィルタリング (`filter_messages_by_relevance`)

計算された関連度スコアが閾値以下のメッセージを除外します。

- **デフォルト閾値**: 0.3
- 閾値は `DEFAULT_RELEVANCE_THRESHOLD` 定数で調整可能

### チャンク生成時の統合

`chunk_messages_with_session_tracking` 関数内で、チャンク生成前にフィルタリングを実行します。

```python
# フィルタリングを有効化（デフォルト）
chunk_data = chunk_messages_with_session_tracking(
    sorted_messages_df,
    max_tokens_per_chunk=8000,
    filter_irrelevant=True,  # フィルタリングを有効化
    relevance_threshold=0.3,  # 閾値を指定
)

# フィルタリングを無効化
chunk_data = chunk_messages_with_session_tracking(
    sorted_messages_df,
    max_tokens_per_chunk=8000,
    filter_irrelevant=False,  # フィルタリングを無効化
)
```

## ロギング

### 統計情報の出力

フィルタリング実行時に、以下の統計情報がINFOレベルで出力されます：

```
メッセージフィルタリング完了: 全1000件 → 750件に削減 (除外: 250件, 25.0%)
```

### デバッグ情報の出力

DEBUGレベルでは、以下の詳細情報が出力されます：

- 除外されたメッセージの具体例（最大10件）
- 各メッセージのスコアとマッチしたキーワード

## 設定のカスタマイズ

### 閾値の調整

`src/intv_comp/analyze/message_filter.py` の `DEFAULT_RELEVANCE_THRESHOLD` を変更します：

```python
# より厳しくフィルタリング（多くのメッセージを除外）
DEFAULT_RELEVANCE_THRESHOLD = 0.5

# より緩くフィルタリング（少ないメッセージを除外）
DEFAULT_RELEVANCE_THRESHOLD = 0.2
```

### キーワードの追加

`BILL_RELATED_KEYWORDS` リストにキーワードを追加します：

```python
BILL_RELATED_KEYWORDS = [
    # 既存のキーワード...
    "新しいキーワード1",
    "新しいキーワード2",
]
```

## 使用例

```python
import pandas as pd
from intv_comp.analyze.message_filter import (
    filter_messages_by_relevance,
    calculate_relevance_score,
)

# 個別メッセージのスコア計算
score = calculate_relevance_score("船荷証券の電子化法案について意見があります")
print(f"スコア: {score}")  # スコア: 0.8

# DataFrameのフィルタリング
df = pd.read_csv("messages.csv")
filtered_df = filter_messages_by_relevance(df, threshold=0.3)
```

## 注意事項

1. **キーワードベースの制約**: 現在の実装はキーワードマッチングベースのため、文脈を完全には理解できません
2. **日本語特化**: キーワードリストは日本語に特化しています
3. **閾値の調整**: データの特性に応じて閾値の調整が必要な場合があります

## 今後の改善案

1. **LLMベースの判定**: より高度な文脈理解のため、LLMを使用した関連度判定
2. **機械学習モデル**: 教師データを使用した機械学習ベースのフィルタリング
3. **動的閾値調整**: データの分布に応じた自動閾値調整
4. **多言語対応**: 英語など他言語のサポート
