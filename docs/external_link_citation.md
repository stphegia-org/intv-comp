# 外部リンク引用対応機能

## 概要

政策レポート生成機能では、インタビュー内容を引用する際に外部公開URLを必ず付与することで、情報の透明性と信頼性を向上させます。

## 主な機能

### 1. 政策単位のレポート生成

従来のチャンク分析モードに加えて、新しい「政策モード」で政策ごとに1本のレポートを生成できます。

### 2. 5部構成のレポートフォーマット

政策レポートは以下の5つのセクションで構成されます：

1. **Executive Summary（3〜5行）**
   - インタビュー固有の示唆のみをまとめた短い要約

2. **触れられていない論点（Blind Spots）**
   - 議論されていないが政策判断上重要となり得る論点

3. **回答の一貫性・揺らぎ**
   - 主要概念についての一貫性・矛盾・揺らぎを整理
   - 引用は短く（2〜3行）

4. **回答が示す意味の整理（Implication Clarity）**
   - 回答内容が示す前提・方向性を明確化し、判断材料を高解像度で提示

5. **主要原文引用**
   - 本文に載せきれないが重要な引用を掲載（すべて ID＋外部リンク付き）

### 3. 外部リンク必須の引用フォーマット

全ての引用には以下の情報が付与されます：

```markdown
> 「……引用本文……」
> 出典：セッションID：S-001 / 発言ID：M-045
> 出典元リンク：https://www.example.go.jp/document.pdf
```

## 使用方法

### 準備

1. **外部情報参照リストの作成**

   `data/references/external_info_reference_template.md` ファイルを作成し、以下のフォーマットで外部文書情報を記載します：

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

2. **.envファイルの設定**

   `.env` ファイルに以下の設定を追加します：

   ```bash
   EXTERNAL_SOURCES_FILE=data/references/external_info_reference_template.md
   ```

### 実行

政策モードでレポートを生成するには、`--policy-mode` フラグを使用します：

```bash
python -m intv_comp.analyze.analyze_interviews \
  --policy-mode \
  --messages-file data/raw/bill-of-lading_messages.csv \
  --sessions-file data/raw/bill-of-lading_interview_sessions.csv \
  --output output/policy_report.md \
  --external-sources-file data/references/external_info_reference_template.md
```

### オプション

- `--policy-mode`: 政策単位でレポートを生成するモード（新仕様）
- `--external-sources-file`: 外部情報参照リストファイルのパス
- `--references-dir`: 追加資料（参考資料）が格納されているディレクトリのパス
- `--model`: 使用するOpenAIモデル名（デフォルト: gpt-4.1）

## 技術仕様

### データクラス

#### PolicyConversation

政策単位でメッセージを集約するデータクラス：

```python
@dataclass
class PolicyConversation:
    policy_id: str
    title: str
    messages: List[MessageInfo]
```

#### MessageInfo

メッセージ情報を保持するデータクラス：

```python
@dataclass
class MessageInfo:
    session_id: str
    message_id: str
    timestamp: str
    role: str
    content: str
```

#### ExternalDocument

外部文書情報を保持するデータクラス：

```python
@dataclass
class ExternalDocument:
    doc_id: str
    title: str
    url: str
    description: str
```

### 主要関数

- `load_external_sources(file_path: Path) -> ExternalSourcesRepository`
  - 外部情報参照リストファイルを読み込む

- `build_policy_from_messages(messages_df, sessions_df, policy_id) -> PolicyConversation`
  - メッセージDataFrameから政策会話データを構築する

- `render_policy_report(policy, llm_client, external_sources, reference_materials) -> str`
  - 政策レポートのMarkdown文字列を生成する

- `build_policy_analysis_prompt(policy, external_sources, reference_materials) -> str`
  - 政策単位の分析を行うためのプロンプトを生成する

## 注意事項

- 一般論や抽象的な内容は禁止されており、インタビュー固有の具体的な内容のみが扱われます
- 引用は短く（2〜3行以内）にすることが推奨されます
- 全ての引用には必ず外部公開URLを付与する必要があります
- 外部URLが見つからない場合は、デフォルトでdepth-interview-aiのリンクが使用されます

## トラブルシューティング

### 外部情報参照リストが読み込まれない

- ファイルパスが正しいか確認してください
- ファイルのフォーマットが正しいか確認してください（Markdown形式）
- `.env` ファイルの `EXTERNAL_SOURCES_FILE` 設定を確認してください

### 政策レポートが生成されない

- `--policy-mode` フラグを付けているか確認してください
- メッセージCSVファイルとセッションCSVファイルが存在するか確認してください
- OpenAI APIキーが正しく設定されているか確認してください（`.env` ファイル）

### 型エラーが発生する

- 仮想環境が有効化されているか確認してください: `source .venv/bin/activate`
- 依存パッケージがインストールされているか確認してください: `uv sync`
