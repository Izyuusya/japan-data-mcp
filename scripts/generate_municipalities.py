"""総務省の標準地域コード CSV から municipalities.json を生成する.

Usage:
    uv run python scripts/generate_municipalities.py

ソース:
    https://www.soumu.go.jp/main_content/000323625.csv
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CSV_PATH = SCRIPT_DIR / "soumu_area_codes.csv"
OUTPUT_PATH = (
    SCRIPT_DIR.parent / "src" / "japan_data_mcp" / "data" / "municipalities.json"
)


def main() -> None:
    municipalities: dict[str, str] = {}

    with CSV_PATH.open(encoding="shift_jis") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["tiiki-code"].strip()
            ken_name = row["ken-name"].strip()
            name1 = row["sityouson-name1"].strip()  # 政令市名 or 郡名
            name2 = row["sityouson-name2"].strip()  # 支庁名
            name3 = row["sityouson-name3"].strip()  # 市区町村名

            # 都道府県行（XX000）はスキップ
            if code.endswith("000"):
                continue

            # 市区町村名を決定
            # name3 があればそれが市区町村名（郡部の町村、政令市の区）
            # name3 がなく name1 があれば政令市名や一般市名
            if name3:
                area_name = name3
            elif name1:
                area_name = name1
            else:
                continue  # 名前が取れない行はスキップ

            # 同名市区町村の処理（例: 府中市が東京都と広島県に存在）
            if area_name in municipalities:
                # 既に登録済みの場合、都道府県名付きで両方登録
                existing_code = municipalities.pop(area_name)
                # 既存エントリの都道府県名を逆引きで取得
                existing_ken = _find_ken_for_code(
                    existing_code, CSV_PATH
                )
                municipalities[f"{area_name}（{existing_ken}）"] = existing_code
                municipalities[f"{area_name}（{ken_name}）"] = code
            elif f"{area_name}（" in "".join(municipalities.keys()):
                # 既に都道府県名付きで登録済みの同名市区町村がある
                municipalities[f"{area_name}（{ken_name}）"] = code
            else:
                municipalities[area_name] = code

    # コード順でソート
    sorted_data = dict(
        sorted(municipalities.items(), key=lambda x: x[1])
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=2)

    print(f"Generated {OUTPUT_PATH}")
    print(f"Total entries: {len(sorted_data)}")

    # サンプル表示
    samples = ["水戸市", "宇都宮市", "前橋市", "府中市（東京都）", "府中市（広島県）"]
    for name in samples:
        code = sorted_data.get(name, "NOT FOUND")
        print(f"  {name}: {code}")


def _find_ken_for_code(code: str, csv_path: Path) -> str:
    """コードから都道府県名を逆引きする."""
    with csv_path.open(encoding="shift_jis") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["tiiki-code"].strip() == code:
                return row["ken-name"].strip()
    return ""


if __name__ == "__main__":
    main()
