"""地域コードの定義と名称→コード変換.

都道府県（47 + 全国）、政令指定都市（20市）、
および全国市区町村（約1,700）を収録。
"""

from __future__ import annotations

import json
from pathlib import Path

# e-Stat 都道府県コード（5桁）
PREFECTURE_CODES: dict[str, str] = {
    "全国": "00000",
    "北海道": "01000",
    "青森県": "02000",
    "岩手県": "03000",
    "宮城県": "04000",
    "秋田県": "05000",
    "山形県": "06000",
    "福島県": "07000",
    "茨城県": "08000",
    "栃木県": "09000",
    "群馬県": "10000",
    "埼玉県": "11000",
    "千葉県": "12000",
    "東京都": "13000",
    "神奈川県": "14000",
    "新潟県": "15000",
    "富山県": "16000",
    "石川県": "17000",
    "福井県": "18000",
    "山梨県": "19000",
    "長野県": "20000",
    "岐阜県": "21000",
    "静岡県": "22000",
    "愛知県": "23000",
    "三重県": "24000",
    "滋賀県": "25000",
    "京都府": "26000",
    "大阪府": "27000",
    "兵庫県": "28000",
    "奈良県": "29000",
    "和歌山県": "30000",
    "鳥取県": "31000",
    "島根県": "32000",
    "岡山県": "33000",
    "広島県": "34000",
    "山口県": "35000",
    "徳島県": "36000",
    "香川県": "37000",
    "愛媛県": "38000",
    "高知県": "39000",
    "福岡県": "40000",
    "佐賀県": "41000",
    "長崎県": "42000",
    "熊本県": "43000",
    "大分県": "44000",
    "宮崎県": "45000",
    "鹿児島県": "46000",
    "沖縄県": "47000",
}

# 政令指定都市コード（5桁）
DESIGNATED_CITY_CODES: dict[str, str] = {
    "札幌市": "01100",
    "仙台市": "04100",
    "さいたま市": "11100",
    "千葉市": "12100",
    "横浜市": "14100",
    "川崎市": "14130",
    "相模原市": "14150",
    "新潟市": "15100",
    "静岡市": "22100",
    "浜松市": "22130",
    "名古屋市": "23100",
    "京都市": "26100",
    "大阪市": "27100",
    "堺市": "27140",
    "神戸市": "28100",
    "岡山市": "33100",
    "広島市": "34100",
    "北九州市": "40100",
    "福岡市": "40130",
    "熊本市": "43100",
}

# 市区町村コード（JSON からロード）
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MUNICIPALITIES_PATH = _DATA_DIR / "municipalities.json"


def _load_municipality_codes() -> dict[str, str]:
    """municipalities.json から市区町村コードを読み込む."""
    if not _MUNICIPALITIES_PATH.exists():
        return {}
    with _MUNICIPALITIES_PATH.open(encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


MUNICIPALITY_CODES: dict[str, str] = _load_municipality_codes()

# 全地域コード（都道府県 + 政令指定都市 + 市区町村）
ALL_AREA_CODES: dict[str, str] = {
    **PREFECTURE_CODES,
    **DESIGNATED_CITY_CODES,
    **MUNICIPALITY_CODES,
}

# コード → 名称の逆引き
CODE_TO_AREA: dict[str, str] = {v: k for k, v in ALL_AREA_CODES.items()}

# 後方互換
CODE_TO_PREFECTURE = CODE_TO_AREA


class AmbiguousAreaError(Exception):
    """地域名が複数の地域に一致した場合のエラー."""

    def __init__(self, query: str, matches: list[tuple[str, str]]) -> None:
        self.query = query
        self.matches = matches
        candidates = "\n".join(
            f"  - {name}（コード: {code}）" for name, code in matches
        )
        super().__init__(
            f"「{query}」は複数の地域に一致します。"
            f"正確な地域名またはコードを指定してください:\n{candidates}\n\n"
            f"> ヒント: `resolve_area` ツールで地域コードを確認できます。"
        )


def resolve_area_code(query: str) -> list[tuple[str, str]]:
    """地域名から地域コードを検索する.

    完全一致 → 前方一致 → 部分一致の優先順で検索。
    都道府県・政令指定都市・市区町村を対象とする。

    「東京」→「東京都」、「福岡市」→「福岡市(40130)」のように
    接尾辞なしでもマッチする。

    Args:
        query: 検索する地域名（例: "東京", "福岡市", "大阪"）

    Returns:
        (地域名, 地域コード) のリスト。マッチ順。
    """
    query = query.strip()
    if not query:
        return []

    # 完全一致
    if query in ALL_AREA_CODES:
        return [(query, ALL_AREA_CODES[query])]

    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    # 前方一致（「福岡」→「福岡県」「福岡市」）
    for name, code in ALL_AREA_CODES.items():
        if name.startswith(query) and name not in seen:
            results.append((name, code))
            seen.add(name)

    # 部分一致（前方一致で見つからなかった場合のフォールバック）
    if not results:
        for name, code in ALL_AREA_CODES.items():
            if query in name and name not in seen:
                results.append((name, code))
                seen.add(name)

    return results
