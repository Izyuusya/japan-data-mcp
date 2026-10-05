"""不動産取引データの整形モジュール."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from japan_data_mcp.realestate.models import LandPrice, Transaction

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


# ------------------------------------------------------------------
# 地価公示・地価調査（XPT002）の整形
# ------------------------------------------------------------------


def format_land_prices(
    land_prices: list[LandPrice],
    *,
    area_name: str | None = None,
    year: int | None = None,
    price_classification: str | None = None,
    use_category: str | None = None,
    saturated: bool = True,
    limit: int = 50,
) -> str:
    """地価公示・地価調査の地点データをマークダウンレポートに整形する."""
    if not land_prices:
        return _no_land_price_message(area_name, year)

    lines: list[str] = []
    header = "## 地価公示・地価調査"
    if area_name:
        header += f": {area_name}"
    lines.append(header)
    lines.append(f"*全{len(land_prices)}地点*\n")

    summary = _build_land_price_summary(land_prices)
    if summary:
        lines.append(summary)

    lines.append(_build_land_price_table(land_prices, limit=limit))
    if len(land_prices) > limit:
        lines.append(f"\n*（価格上位{limit}地点を表示。全{len(land_prices)}地点）*")

    lines.append(
        _build_land_price_footer(
            area_name=area_name,
            year=year,
            price_classification=price_classification,
            use_category=use_category,
            saturated=saturated,
        )
    )
    return "\n".join(lines)


def _no_land_price_message(area_name: str | None, year: int | None) -> str:
    label = area_name or "指定地域"
    suffix = f"（{year}年）" if year else ""
    return (
        f"## 地価公示・地価調査: {label}{suffix}\n\n"
        f"{label} の地価データは見つかりませんでした。\n\n"
        "> 年・地域・用途区分を変更してお試しください。"
        "地価公示は毎年3月下旬に公表され、対象年（1月1日現在）のデータが取得できます。"
    )


def _build_land_price_summary(land_prices: list[LandPrice]) -> str:
    """用途区分ごとの中央値・平均と、対前年変動率のサマリーを生成する."""
    by_use: dict[str, list[int]] = {}
    for lp in land_prices:
        price = lp.price_int
        if price is None or price <= 0:
            continue
        by_use.setdefault(lp.use_category_name_ja or "その他", []).append(price)

    lines: list[str] = ["### 価格サマリー（円/㎡）"]
    if by_use:
        lines.append("| 用途区分 | 地点数 | 中央値 | 平均 | 最小 | 最大 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for use, prices in sorted(
            by_use.items(), key=lambda kv: -statistics.median(kv[1])
        ):
            lines.append(
                f"| {use} | {len(prices)} | {int(statistics.median(prices)):,} "
                f"| {int(statistics.mean(prices)):,} | {min(prices):,} "
                f"| {max(prices):,} |"
            )
    else:
        lines.append("- 価格を数値化できる地点がありませんでした。")

    rates = [lp.yoy_rate_float for lp in land_prices]
    rates = [r for r in rates if r is not None]
    if rates:
        up = sum(1 for r in rates if r > 0)
        lines.append("")
        lines.append(
            f"- 対前年変動率: 平均 {statistics.mean(rates):+.1f}% "
            f"/ 中央値 {statistics.median(rates):+.1f}% "
            f"/ 上昇 {up}/{len(rates)} 地点"
        )

    lines.append("")
    return "\n".join(lines)


def _build_land_price_table(land_prices: list[LandPrice], *, limit: int) -> str:
    """価格の高い順に地点テーブルを生成する."""
    ordered = sorted(
        land_prices, key=lambda lp: (lp.price_int is None, -(lp.price_int or 0))
    )[:limit]
    headers = ["標準地番号", "用途", "価格", "前年比", "所在地", "最寄駅", "用途地域"]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for lp in ordered:
        yoy = lp.yoy_rate_float
        yoy_display = f"{yoy:+.1f}%" if yoy is not None else "-"
        location = f"{lp.place_name_ja}{lp.location_number_ja}" or "-"
        station = lp.nearest_station_name_ja or "-"
        distance = lp.u_road_distance_to_nearest_station_name_ja
        if station != "-" and distance:
            station = f"{station} {distance}"
        lines.append(
            "| "
            + " | ".join(
                [
                    lp.standard_lot_number_ja or "-",
                    lp.use_category_name_ja or "-",
                    lp.price_display,
                    yoy_display,
                    location,
                    station,
                    lp.regulations_use_category_name_ja or "-",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _build_land_price_footer(
    *,
    area_name: str | None = None,
    year: int | None = None,
    price_classification: str | None = None,
    use_category: str | None = None,
    saturated: bool = True,
) -> str:
    """地価データの検証用フッターを生成する."""
    now = datetime.now(_JST).strftime("%Y-%m-%d %H:%M JST")
    lines = ["", "---", "**データ検証情報**"]
    lines.append("- 出典: 国土交通省 不動産情報ライブラリ（地価公示・地価調査）")
    lines.append(
        "- 不動産情報ライブラリで確認: https://www.reinfolib.mlit.go.jp/"
    )
    lines.append("- API: XPT002（地価公示・地価調査ポイントAPI）")

    search_parts: list[str] = []
    if area_name:
        search_parts.append(area_name)
    if year:
        search_parts.append(f"{year}年")
    if price_classification == "0":
        search_parts.append("国土交通省地価公示のみ")
    elif price_classification == "1":
        search_parts.append("都道府県地価調査のみ")
    if use_category:
        search_parts.append(f"用途区分コード={use_category}")
    if search_parts:
        lines.append(f"- 検索条件: {' / '.join(search_parts)}")

    if not saturated:
        lines.append(
            "- ⚠ 検索範囲の上限に達しても地点が増え続けたため、"
            "市域の一部が欠落している可能性があります。"
            "用途区分や年で絞るか、より狭い地域を指定してください。"
        )
    lines.append(
        "- ⚠ 地価公示・地価調査は「標準地」の正常な価格であり、"
        "実際の取引価格とは異なります（取引事例は get_real_estate_transactions を参照）。"
    )
    lines.append(f"- データ取得日時: {now}")
    return "\n".join(lines)
