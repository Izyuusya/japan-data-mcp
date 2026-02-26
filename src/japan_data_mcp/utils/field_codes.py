"""e-Stat 統計分野コードの定義."""

from __future__ import annotations

# e-Stat 統計分野コード（2桁）
# https://www.e-stat.go.jp/classifications/terms/10
STATS_FIELD_CODES: dict[str, str] = {
    "01": "国土・気象",
    "02": "人口・世帯",
    "03": "労働・賃金",
    "04": "農林水産業",
    "05": "鉱工業",
    "06": "商業・サービス業",
    "07": "企業・家計・経済",
    "08": "住宅・土地・建設",
    "09": "エネルギー・水",
    "10": "運輸・観光",
    "11": "情報通信・科学技術",
    "12": "教育・文化・スポーツ・生活",
    "13": "行財政",
    "14": "司法・安全・環境",
    "15": "社会保障・衛生",
    "16": "国際",
    "17": "その他",
}


def list_stats_fields() -> list[dict[str, str]]:
    """利用可能な統計分野の一覧を返す.

    Returns:
        [{"code": "01", "name": "国土・気象"}, ...] のリスト
    """
    return [
        {"code": code, "name": name}
        for code, name in STATS_FIELD_CODES.items()
    ]
