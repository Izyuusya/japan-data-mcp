"""フォーク実装の実地検証（実API）.

使い方:
  .venv/bin/python -m scripts.verify_fork

以下を実測で確認する:
1. get_land_price(佐倉市, 2026) が XPT002 の地点を返す（境界ベースのタイル列挙）
2. 用途区分フィルタ（住宅地=00）が効く
3. year を省略しても XIT001 の 400 にならない（当年補完）
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# .env からキーを読む（Hermes のランチャーと同じ解決順）
env_file = Path.home() / ".hermes" / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("REALESTATE_API_KEY="):
            os.environ.setdefault(
                "REALESTATE_API_KEY", line.split("=", 1)[1].strip().strip('"').strip("'")
            )
        if line.startswith("ESTAT_APP_ID="):
            os.environ.setdefault(
                "ESTAT_APP_ID", line.split("=", 1)[1].strip().strip('"').strip("'")
            )

from japan_data_mcp.realestate.client import RealEstateClient  # noqa: E402
from japan_data_mcp.realestate.formatter import format_land_prices  # noqa: E402
from japan_data_mcp.realestate.models import RealEstateApiError  # noqa: E402


async def main() -> int:
    ok = True
    async with RealEstateClient() as client:
        # --- 1) 地価公示（佐倉市 2026, 段階拡張で飽和判定） ---
        print("=" * 60)
        print("1) get_land_prices('12', city_code='12212', year=2026)")
        prices, saturated = await client.get_land_prices(
            "12", city_code="12212", year=2026, area_query="千葉県佐倉市"
        )
        print(f"   地点数={len(prices)}  飽和（全域を覆えた）={saturated}")
        assert len(prices) >= 60, f"地点数が少なすぎる: {len(prices)}"
        assert saturated, "検索範囲が飽和していない（市域の取りこぼし）"
        prices_sorted = sorted(
            [p for p in prices if p.price_int], key=lambda p: -p.price_int
        )
        print("   --- 価格上位5地点 ---")
        for p in prices_sorted[:5]:
            print(
                f"   {p.price_display:>12} [{p.use_category_name_ja}] "
                f"前年比{p.year_on_year_change_rate or '-'}% "
                f"{p.place_name_ja}{p.location_number_ja} "
                f"最寄:{p.nearest_station_name_ja}"
            )
        # 既知の値（前セッションの生REST実測）と突き合わせ
        top = prices_sorted[0]
        assert top.price_int == 175000, f"最高額が想定と違う: {top.price_int}"
        assert top.use_category_name_ja == "商業地"

        # --- 2) 用途区分フィルタ（住宅地=00） ---
        print("=" * 60)
        print("2) use_category='00'（住宅地のみ）")
        houses, _ = await client.get_land_prices(
            "12", city_code="12212", year=2026, use_category="00",
            area_query="千葉県佐倉市",
        )
        uses = {p.use_category_name_ja for p in houses}
        print(f"   地点数={len(houses)}  用途区分={uses}")
        assert uses == {"住宅地"}, f"用途フィルタが効いていない: {uses}"
        assert 40 <= len(houses) <= 60

        # --- 3) year 省略時に XIT001 が 400 にならない ---
        print("=" * 60)
        print("3) get_transactions(year 省略) — 当年補完で 400 を回避")
        try:
            txns = await client.get_transactions("12", city_code="12212")
            print(f"   取引件数={len(txns)}（当年=2026 で補完）")
        except RealEstateApiError as e:
            print(f"   ✗ 400 が再発: {e.message}")
            ok = False

        # --- 4) フォーマッタの出力確認 ---
        print("=" * 60)
        print("4) format_land_prices の出力（先頭25行）")
        report = format_land_prices(
            prices, area_name="佐倉市", year=2026, saturated=saturated, limit=10
        )
        for line in report.splitlines()[:25]:
            print("   " + line)
        assert "地価公示・地価調査" in report
        assert "175,000円/㎡" in report

    print("=" * 60)
    print("結果:", "PASS ✅" if ok else "FAIL ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
