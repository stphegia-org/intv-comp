"""インタビューセッションのCSVファイルをJSONに変換するメインスクリプト."""

from pathlib import Path

from intv_comp.converter import convert_csv_to_json


def main() -> None:
    """メイン処理: CSVをJSONに変換する."""
    # プロジェクトのルートディレクトリを取得
    project_root = Path(__file__).parent.parent.parent

    # 入力CSVファイルと出力JSONファイルのパスを定義
    csv_path = project_root / "data" / "raw" / "bill-of-lading_interview_sessions.csv"
    json_path = project_root / "data" / "convert" / "bill-of-lading_interview_sessions.json"

    # 変換を実行
    convert_csv_to_json(csv_path, json_path)


if __name__ == "__main__":
    main()
