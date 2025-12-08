# クイックスタートガイド：政策モードレポート生成

このガイドでは、外部リンク引用対応の政策モードでレポートを生成する手順を説明します。

## 前提条件

1. Python 3.14以降がインストールされていること
2. OpenAI APIキーを取得していること
3. リポジトリをクローンし、依存パッケージをインストール済みであること

## セットアップ

### 1. 環境変数の設定

`.env` ファイルを作成し、以下の内容を設定します：

```bash
# OpenAI API設定
OPENAI_API_KEY=your_actual_api_key_here
OPENAI_MODEL=gpt-4o

# データファイルのパス
MESSAGES_CSV_PATH=data/raw/bill-of-lading_messages.csv
SESSIONS_CSV_PATH=data/raw/bill-of-lading_interview_sessions.csv
REPORT_OUTPUT_PATH=output/policy_report.md

# 参考資料のディレクトリ
REFERENCES_DIR=data/references

# 外部情報参照リストファイル
EXTERNAL_SOURCES_FILE=data/references/external_info_reference_template.md
```

### 2. 外部情報参照リストの準備

`data/references/external_info_reference_template.md` ファイルを編集し、実際の外部URLを記載します：

```markdown
# 外部情報参照リスト

## 法案・審議会資料

- **文書ID**: DOC001
- **タイトル**: 船荷証券の電子化に関する法律案
- **URL**: https://www.moj.go.jp/content/001234567.pdf
- **説明**: 法務省による船荷証券電子化の法律案

## セッション別引用マッピング

### セッション: c2c8334f-1460-44e4-8769-024624dc8f5f

- **関連文書**: DOC001, DOC002
- **説明**: 電子化のメリットとセキュリティに関する議論
```

## 実行方法

### 基本的な実行

```bash
# 仮想環境を有効化
source .venv/bin/activate

# 政策モードでレポート生成
python -m intv_comp.analyze.analyze_interviews --policy-mode
```

### カスタムパラメータを指定した実行

```bash
python -m intv_comp.analyze.analyze_interviews \
  --policy-mode \
  --messages-file data/raw/bill-of-lading_messages.csv \
  --sessions-file data/raw/bill-of-lading_interview_sessions.csv \
  --output output/policy_report_custom.md \
  --external-sources-file data/references/external_info_reference_template.md \
  --model gpt-4o \
  --references-dir data/references
```

### 従来モード（チャンク分析）との比較

```bash
# 従来モード（チャンク分析）
python -m intv_comp.analyze.analyze_interviews

# 新モード（政策レポート）
python -m intv_comp.analyze.analyze_interviews --policy-mode
```

## 出力の確認

生成されたレポートは `output/policy_report.md` に保存されます。

レポートは以下の5つのセクションで構成されます：

1. **Executive Summary（3〜5行）**
   - インタビュー固有の示唆のみをまとめた短い要約

2. **触れられていない論点（Blind Spots）**
   - 議論されていないが政策判断上重要となり得る論点

3. **回答の一貫性・揺らぎ**
   - 主要概念についての一貫性・矛盾・揺らぎを整理
   - 引用は短く（2〜3行）

4. **回答が示す意味の整理（Implication Clarity）**
   - 回答内容が示す前提・方向性を明確化

5. **主要原文引用**
   - 重要な引用（すべてID＋外部リンク付き）

### 引用フォーマットの例

```markdown
> 「電子化により業務効率が大幅に向上すると考えています」
> 出典：セッションID：c2c8334f-1460-44e4-8769-024624dc8f5f / 発言ID：msg-00123
> 出典元リンク：https://www.moj.go.jp/content/001234567.pdf
```

## トラブルシューティング

### エラー: "環境変数が設定されていません"

→ `.env` ファイルを作成し、必要な環境変数を設定してください。

### エラー: "外部情報参照リストが読み込めません"

→ `data/references/external_info_reference_template.md` ファイルが存在するか確認してください。

### エラー: "OpenAI API呼び出しエラー"

→ OpenAI APIキーが正しく設定されているか、APIの利用制限に達していないか確認してください。

### レポートに外部リンクが付与されない

→ 外部情報参照リストにセッションIDのマッピングが登録されているか確認してください。

## より詳しい情報

- [外部リンク引用対応機能の詳細ドキュメント](external_link_citation.md)
- [README.md](../README.md)

## サポート

問題が発生した場合は、GitHub Issuesで報告してください。
