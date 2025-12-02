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
    """
    # CSVファイルを読み込んでリストに変換
    data = []
    with csv_path.open("r", encoding="utf-8") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            data.append(row)

    # JSONファイルに書き込み
    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=2)

    print(f"変換完了: {len(data)}件のレコードを {json_path} に出力しました")
