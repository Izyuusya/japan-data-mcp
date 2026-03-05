"""不動産取引価格 API クライアントとフォーマッタのユニットテスト."""

import pytest

from japan_data_mcp.realestate.client import RealEstateClient
from japan_data_mcp.realestate.formatter import (
    _build_summary,
    _build_table,
    _yen_display,
    format_transactions,
)
from japan_data_mcp.realestate.models import (
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
