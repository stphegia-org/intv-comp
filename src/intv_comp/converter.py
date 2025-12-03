"""CSVファイルをJSONファイルに変換するモジュール."""

import csv
import json
from pathlib import Path


def convert_csv_to_json(
    csv_path: Path,
    json_path: Path,
) -> None:
    """CSVファイルをJSONファイルに変換する.

    Args:
        csv_path: 変換元のCSVファイルパス
        json_path: 変換先のJSONファイルパス

    Raises:
        FileNotFoundError: CSVファイルが存在しない場合
        PermissionError: ファイルへのアクセス権限がない場合
        ValueError: CSVファイルの形式が不正な場合
    """
    # 出力ディレクトリが存在しない場合は作成
    json_path.parent.mkdir(parents=True, exist_ok=True)

    # CSVファイルを読み込んでリストに変換
    data = []
    try:
        with csv_path.open("r", encoding="utf-8") as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                data.append(row)
    except FileNotFoundError:
        raise FileNotFoundError(f"CSVファイルが見つかりません: {csv_path}")
    except PermissionError:
        raise PermissionError(f"CSVファイルへのアクセス権限がありません: {csv_path}")

    # JSONファイルに書き込み
    try:
        with json_path.open("w", encoding="utf-8") as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=2)
    except PermissionError:
        raise PermissionError(f"JSONファイルへの書き込み権限がありません: {json_path}")

    print(f"変換完了: {len(data)}件のレコードを {json_path} に出力しました")
