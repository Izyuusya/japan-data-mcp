"""不動産取引価格 API クライアントとフォーマッタのユニットテスト."""

import pytest

from japan_data_mcp.realestate.client import RealEstateClient, current_year_jst
from japan_data_mcp.realestate.formatter import (
    _build_summary,
    _build_land_price_summary,
    _build_land_price_table,
    _build_table,
    _yen_display,
    format_land_prices,
    format_transactions,
)
from japan_data_mcp.realestate.models import (
    LandPrice,
    Municipality,
    RealEstateApiError,
    Transaction,
)

# ------------------------------------------------------------------
# モデルのテスト
# ------------------------------------------------------------------


def _sample_transaction(**kwargs) -> Transaction:
    defaults = {
        "transaction_type": "宅地(土地と建物)",
        "trade_price": "35000000",
        "area": "100",
        "municipality_code": "08201",
        "prefecture": "茨城県",
        "municipality": "水戸市",
        "district_name": "笠原町",
        "region": "住宅地",
        "building_year": "2010年",
        "period": "第１四半期",
    }
    defaults.update(kwargs)
    return Transaction(**defaults)


class TestTransactionModel:
    def test_trade_price_int(self):
        t = _sample_transaction(trade_price="35000000")
        assert t.trade_price_int == 35_000_000

    def test_trade_price_int_invalid(self):
        t = _sample_transaction(trade_price="非公開")
        assert t.trade_price_int is None

    def test_trade_price_display_man(self):
        t = _sample_transaction(trade_price="35000000")
        assert t.trade_price_display == "3,500万円"

    def test_trade_price_display_oku(self):
        t = _sample_transaction(trade_price="150000000")
        assert t.trade_price_display == "1億5,000万円"

    def test_trade_price_display_oku_even(self):
        t = _sample_transaction(trade_price="100000000")
        assert t.trade_price_display == "1億円"

    def test_trade_price_display_small(self):
        t = _sample_transaction(trade_price="5000")
        assert t.trade_price_display == "5,000円"

    def test_trade_price_display_empty(self):
        t = _sample_transaction(trade_price="")
        assert t.trade_price_display == "-"

    def test_alias_validation(self):
        """APIレスポンスのフィールド名（alias）でもバリデーションできる."""
        t = Transaction.model_validate({
            "Type": "宅地(土地と建物)",
            "TradePrice": "35000000",
            "Area": "100",
            "MunicipalityCode": "08201",
            "Prefecture": "茨城県",
            "Municipality": "水戸市",
        })
        assert t.transaction_type == "宅地(土地と建物)"
        assert t.trade_price == "35000000"


class TestMunicipalityModel:
    def test_alias_validation(self):
        m = Municipality.model_validate({"id": "08201", "name": "水戸市"})
        assert m.code == "08201"
        assert m.name == "水戸市"


# ------------------------------------------------------------------
# フォーマッタのテスト
# ------------------------------------------------------------------


class TestYenDisplay:
    def test_oku(self):
        assert _yen_display(150_000_000) == "1億5,000万円"

    def test_oku_even(self):
        assert _yen_display(100_000_000) == "1億円"

    def test_man(self):
        assert _yen_display(3_500_000) == "350万円"

    def test_small(self):
        assert _yen_display(5_000) == "5,000円"

    def test_zero(self):
        assert _yen_display(0) == "0円"


class TestBuildSummary:
    def test_basic_summary(self):
        txns = [
            _sample_transaction(trade_price="30000000"),
            _sample_transaction(trade_price="40000000"),
        ]
        result = _build_summary(txns)
        assert "件数: 2件" in result
        assert "平均取引価格" in result
        assert "中央値" in result

    def test_no_valid_prices(self):
        txns = [_sample_transaction(trade_price="非公開")]
        result = _build_summary(txns)
        assert result == ""

    def test_type_breakdown(self):
        txns = [
            _sample_transaction(transaction_type="宅地(土地と建物)"),
            _sample_transaction(transaction_type="宅地(土地と建物)"),
            _sample_transaction(transaction_type="中古マンション等"),
        ]
        result = _build_summary(txns)
        assert "宅地(土地と建物)(2件)" in result
        assert "中古マンション等(1件)" in result


class TestBuildTable:
    def test_basic_table(self):
        txns = [_sample_transaction()]
        result = _build_table(txns)
        assert "| 種別 |" in result
        assert "笠原町" in result
        assert "3,500万円" in result

    def test_empty_table(self):
        result = _build_table([])
        # ヘッダーのみ
        assert "| 種別 |" in result


class TestFormatTransactions:
    def test_full_report(self):
        txns = [
            _sample_transaction(trade_price="30000000"),
            _sample_transaction(trade_price="40000000"),
        ]
        result = format_transactions(txns, area_name="水戸市", year=2023)

        assert "不動産取引価格情報" in result
        assert "水戸市" in result
        assert "全2件" in result
        assert "データ検証情報" in result
        assert "不動産情報ライブラリ" in result
        assert "2023年" in result

    def test_no_data(self):
        result = format_transactions([], area_name="水戸市")
        assert "見つかりませんでした" in result
        assert "水戸市" in result

    def test_limit_applied(self):
        txns = [_sample_transaction() for _ in range(100)]
        result = format_transactions(txns, limit=10)
        assert "10件まで表示" in result
        assert "全100件" in result


# ------------------------------------------------------------------
# クライアントの初期化テスト
# ------------------------------------------------------------------


class TestRealEstateClientInit:
    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("REALESTATE_API_KEY", raising=False)
        monkeypatch.setattr(
            "japan_data_mcp.realestate.client.load_env_file", lambda: None
        )
        with pytest.raises(ValueError, match="REALESTATE_API_KEY"):
            RealEstateClient()

    def test_accepts_explicit_api_key(self):
        client = RealEstateClient(api_key="test-key")
        assert client._api_key == "test-key"


# ------------------------------------------------------------------
# 地価公示・地価調査（XPT002）のテスト
# ------------------------------------------------------------------


def _sample_land_price(**kwargs) -> LandPrice:
    defaults = {
        "point_id": 3000032,
        "target_year_name_ja": "令和8年1月1日",
        "land_price_type": 0,
        "prefecture_code": "12",
        "prefecture_name_ja": "千葉県",
        "city_code": "12212",
        "city_county_name_ja": "佐倉市",
        "use_category_name_ja": "商業地",
        "standard_lot_number_ja": "佐倉5-1",
        "place_name_ja": "佐倉",
        "location_number_ja": "王子台３丁目１番６外",
        "u_current_years_price_ja": "175,000(円/㎡)",
        "last_years_price": 168000,
        "year_on_year_change_rate": "4.2",
        "nearest_station_name_ja": "京成臼井",
        "u_road_distance_to_nearest_station_name_ja": "140m",
        "regulations_use_category_name_ja": "商業地域",
    }
    defaults.update(kwargs)
    return LandPrice(**defaults)


class TestLandPriceModel:
    def test_price_int(self):
        assert _sample_land_price().price_int == 175_000

    def test_price_int_empty(self):
        assert _sample_land_price(u_current_years_price_ja="").price_int is None

    def test_price_int_unparseable(self):
        assert _sample_land_price(u_current_years_price_ja="非公開").price_int is None

    def test_yoy_rate_float(self):
        assert _sample_land_price().yoy_rate_float == 4.2

    def test_yoy_rate_float_empty(self):
        # 新規地点は変動率が空
        assert _sample_land_price(year_on_year_change_rate="").yoy_rate_float is None

    def test_price_display(self):
        assert _sample_land_price().price_display == "175,000円/㎡"

    def test_price_display_fallback(self):
        assert _sample_land_price(u_current_years_price_ja="").price_display == "-"

    def test_land_price_type_display(self):
        assert _sample_land_price(land_price_type=0).land_price_type_display == "国土交通省地価公示"
        assert _sample_land_price(land_price_type=1).land_price_type_display == "都道府県地価調査"
        assert _sample_land_price(land_price_type=None).land_price_type_display == "-"

    def test_alias_validation(self):
        lp = LandPrice.model_validate(
            {
                "standard_lot_number_ja": "佐倉-6",
                "use_category_name_ja": "住宅地",
                "u_current_years_price_ja": "129,000(円/㎡)",
                "year_on_year_change_rate": "3.2",
                "city_code": "12212",
            }
        )
        assert lp.price_int == 129_000
        assert lp.use_category_name_ja == "住宅地"


class TestBuildLandPriceSummary:
    def test_summary_by_use_category(self):
        prices = [
            _sample_land_price(u_current_years_price_ja="175,000(円/㎡)"),
            _sample_land_price(u_current_years_price_ja="124,000(円/㎡)"),
            _sample_land_price(
                use_category_name_ja="住宅地",
                u_current_years_price_ja="65,800(円/㎡)",
            ),
        ]
        result = _build_land_price_summary(prices)
        assert "商業地" in result
        assert "住宅地" in result
        assert "149,500" in result  # (175,000 + 124,000) / 2
        assert "対前年変動率" in result

    def test_summary_no_prices(self):
        result = _build_land_price_summary([_sample_land_price(u_current_years_price_ja="")])
        assert "数値化できる地点がありませんでした" in result


class TestBuildLandPriceTable:
    def test_table_sorted_by_price_desc(self):
        prices = [
            _sample_land_price(u_current_years_price_ja="10,000(円/㎡)"),
            _sample_land_price(
                standard_lot_number_ja="佐倉-6",
                u_current_years_price_ja="129,000(円/㎡)",
            ),
        ]
        result = _build_land_price_table(prices, limit=10)
        assert "佐倉-6" in result
        # 高額な地点が先に来る
        assert result.index("佐倉-6") < result.index("佐倉5-1")

    def test_table_new_point_yoy_dash(self):
        result = _build_land_price_table(
            [_sample_land_price(year_on_year_change_rate="")], limit=10
        )
        assert "| - |" in result


class TestFormatLandPrices:
    def test_full_report(self):
        prices = [
            _sample_land_price(),
            _sample_land_price(
                standard_lot_number_ja="佐倉-6",
                use_category_name_ja="住宅地",
                u_current_years_price_ja="129,000(円/㎡)",
            ),
        ]
        result = format_land_prices(prices, area_name="佐倉市", year=2026)
        assert "地価公示・地価調査" in result
        assert "佐倉市" in result
        assert "全2地点" in result
        assert "データ検証情報" in result
        assert "XPT002" in result
        assert "175,000円/㎡" in result

    def test_no_data(self):
        result = format_land_prices([], area_name="佐倉市", year=2026)
        assert "見つかりませんでした" in result
        assert "佐倉市" in result

    def test_limit_applied(self):
        prices = [_sample_land_price() for _ in range(100)]
        result = format_land_prices(prices, limit=10)
        assert "全100地点" in result

    def test_unsaturated_warning(self):
        result = format_land_prices([_sample_land_price()], saturated=False)
        assert "一部が欠落している可能性" in result

    def test_trade_warning_present(self):
        result = format_land_prices([_sample_land_price()])
        assert "実際の取引価格とは異なります" in result


class TestCurrentYearJst:
    def test_returns_plausible_year(self):
        assert 2000 <= current_year_jst() <= 2100


class TestGetTransactionsYearDefault:
    """year 未指定でも 400 にならない（当年補完）ことを検証する."""

    @pytest.mark.asyncio
    async def test_year_defaulted_when_omitted(self, monkeypatch):
        client = RealEstateClient(api_key="test-key")
        captured: dict[str, object] = {}

        async def _fake_request(endpoint, params):
            captured["endpoint"] = endpoint
            captured["params"] = params
            return {"data": []}

        monkeypatch.setattr(client, "_request", _fake_request)
        await client.get_transactions("12", city_code="12212")
        assert captured["endpoint"] == "XIT001"
        assert captured["params"]["year"] == current_year_jst()

    @pytest.mark.asyncio
    async def test_explicit_year_preserved(self, monkeypatch):
        client = RealEstateClient(api_key="test-key")
        captured: dict[str, object] = {}

        async def _fake_request(endpoint, params):
            captured["params"] = params
            return {"data": []}

        monkeypatch.setattr(client, "_request", _fake_request)
        await client.get_transactions("12", city_code="12212", year=2023, quarter=2)
        assert captured["params"]["year"] == 2023
        assert captured["params"]["quarter"] == 2


class TestGeoTiles:
    def test_deg2tile_known_tile(self):
        from japan_data_mcp.realestate.geotiles import deg2tile

        # 佐倉市中心部（GSI代表点）は z=13 で (7286, 3224)
        assert deg2tile(140.223969, 35.723492, 13) == (7286, 3224)

    def test_tile_window_size(self):
        from japan_data_mcp.realestate.geotiles import tile_window

        tiles = tile_window(100, 100, 3)
        assert len(tiles) == 7 * 7
        assert (100, 100) in tiles
        assert (97, 97) in tiles
        assert (103, 103) in tiles

    def test_tile_window_max_guard(self):
        from japan_data_mcp.realestate.geotiles import tile_window

        with pytest.raises(ValueError):
            tile_window(100, 100, 50, max_tiles=100)
