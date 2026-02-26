"""不動産取引データの整形モジュール."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from japan_data_mcp.realestate.models import Transaction

_JST = timezone(timedelta(hours=9))


def format_transactions(
    transactions: list[Transaction],
    *,
    area_name: str | None = None,
    year: int | None = None,
    quarter: int | None = None,
    limit: int = 50,
) -> str:
    """取引データをマークダウンレポートに整形する.

    Args:
        transactions: 取引データのリスト
        area_name: 地域名（見出し用）
        year: 取得年（フッター用）
        quarter: 四半期（フッター用）
        limit: 表示する最大件数

    Returns:
        マークダウン形式のレポート
    """
    if not transactions:
        return _no_data_message(area_name)

    lines: list[str] = []

    # ヘッダー
    header = "## 不動産取引価格情報"
    if area_name:
        header += f": {area_name}"
    lines.append(header)
    lines.append(f"*全{len(transactions)}件*\n")

    # サマリー
    summary = _build_summary(transactions)
    if summary:
        lines.append(summary)

    # 一覧テーブル
    display = transactions[:limit]
    lines.append(_build_table(display))

    if len(transactions) > limit:
        lines.append(f"\n*（{limit}件まで表示。全{len(transactions)}件）*")

    # 検証フッター
    lines.append(
        _build_footer(area_name=area_name, year=year, quarter=quarter)
    )

    return "\n".join(lines)


def _no_data_message(area_name: str | None) -> str:
    label = area_name or "指定地域"
    return (
        f"## 不動産取引価格情報: {label}\n\n"
        f"{label} の取引データは見つかりませんでした。\n\n"
        "> 検索年や地域を変更してお試しください。"
    )


def _build_summary(transactions: list[Transaction]) -> str:
    """価格サマリーを生成する."""
    prices = [
        t.trade_price_int
        for t in transactions
        if t.trade_price_int is not None and t.trade_price_int > 0
    ]

    if not prices:
        return ""

    lines: list[str] = ["### 価格サマリー"]
    avg = statistics.mean(prices)
    med = statistics.median(prices)

    lines.append(f"- 件数: {len(prices)}件")
    lines.append(f"- 平均取引価格: {_yen_display(int(avg))}")
    lines.append(f"- 中央値: {_yen_display(int(med))}")
    lines.append(f"- 最高: {_yen_display(max(prices))}")
    lines.append(f"- 最低: {_yen_display(min(prices))}")

    # 種別ごとの件数
    type_counts: dict[str, int] = {}
    for t in transactions:
        key = t.transaction_type or "その他"
        type_counts[key] = type_counts.get(key, 0) + 1
    if type_counts:
        lines.append("- 種別内訳: " + "、".join(
            f"{k}({v}件)" for k, v in sorted(
                type_counts.items(), key=lambda x: -x[1]
            )
        ))

    lines.append("")
    return "\n".join(lines)


def _build_table(transactions: list[Transaction]) -> str:
    """取引データのマークダウンテーブルを生成する."""
    headers = ["種別", "地区", "取引価格", "面積", "建築年", "最寄駅", "時期"]
    lines: list[str] = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")

    for t in transactions:
        row = [
            t.transaction_type,
            t.district_name or t.region,
            t.trade_price_display,
            f"{t.area}㎡" if t.area else "-",
            t.building_year or "-",
            _station_display(t),
            t.period or "-",
        ]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _station_display(t: Transaction) -> str:
    """最寄駅の表示文字列."""
    # Transaction モデルには nearest_station がない場合がある
    # API レスポンスのフィールド名に合わせて取得
    station = getattr(t, "nearest_station", "") or ""
    minutes = getattr(t, "minutes_to_station", None)
    if not station:
        return "-"
    if minutes:
        return f"{station} 徒歩{minutes}分"
    return station


def _yen_display(price: int) -> str:
    """整数を日本円表記に変換（万円）."""
    if price >= 100_000_000:
        oku = price // 100_000_000
        man = (price % 100_000_000) // 10_000
        if man:
            return f"{oku}億{man:,}万円"
        return f"{oku}億円"
    if price >= 10_000:
        return f"{price // 10_000:,}万円"
    return f"{price:,}円"


def _build_footer(
    *,
    area_name: str | None = None,
    year: int | None = None,
    quarter: int | None = None,
) -> str:
    """データ検証用フッターを生成する."""
    now = datetime.now(_JST).strftime("%Y-%m-%d %H:%M JST")
    lines: list[str] = ["", "---", "**データ検証情報**"]
    lines.append("- 出典: 国土交通省 不動産情報ライブラリ")
    lines.append(
        "- 不動産情報ライブラリで確認: https://www.reinfolib.mlit.go.jp/"
    )

    search_parts: list[str] = []
    if area_name:
        search_parts.append(area_name)
    if year:
        label = f"{year}年"
        if quarter:
            label += f"第{quarter}四半期"
        search_parts.append(label)
    if search_parts:
        lines.append(f"- 検索条件: {' / '.join(search_parts)}")

    lines.append(f"- データ取得日時: {now}")
    lines.append(
        "- ⚠ 本データは不動産情報ライブラリ API から自動取得した値をそのまま表示しています。"
        "正確性の最終確認は上記リンクから原本データをご参照ください。"
    )
    return "\n".join(lines)
