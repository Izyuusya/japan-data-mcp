"""MCP サーバーのユニットテスト."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from japan_data_mcp.corp.models import CorpApiError, Corporation
from japan_data_mcp.estat.models import (
    ClassItem,
    ClassObject,
    DataValue,
    MetaInfo,
    StatsData,
    TableInfo,
)
from japan_data_mcp.invoice.models import InvoiceApiError, InvoiceIssuer
from japan_data_mcp.realestate.models import RealEstateApiError, Transaction
from japan_data_mcp.server import (
    _resolve_single_area,
    mcp,
)
from japan_data_mcp.utils.area_codes import AmbiguousAreaError


# ------------------------------------------------------------------
# ヘルパー関数のテスト
# ------------------------------------------------------------------


class TestResolveSingleArea:
    def test_numeric_code_passthrough(self):
        assert _resolve_single_area("13000") == "13000"

    def test_prefecture_name(self):
        assert _resolve_single_area("東京都") == "13000"

    def test_partial_name(self):
        assert _resolve_single_area("東京") == "13000"

    def test_unknown_name_passthrough(self):
        assert _resolve_single_area("存在しない地域") == "存在しない地域"

    def test_ambiguous_name_raises(self):
        """曖昧な地域名で AmbiguousAreaError が発生する."""
        with pytest.raises(AmbiguousAreaError) as exc_info:
            _resolve_single_area("福岡")
        msg = str(exc_info.value)
        assert "福岡県" in msg
        assert "福岡市" in msg
        assert "複数の地域に一致" in msg

    def test_exact_name_with_suffix_not_ambiguous(self):
        """接尾辞付きの完全一致は曖昧にならない."""
        assert _resolve_single_area("福岡県") == "40000"
        assert _resolve_single_area("福岡市") == "40130"
        assert _resolve_single_area("大阪府") == "27000"
        assert _resolve_single_area("大阪市") == "27100"


AMBIGUOUS_PATTERNS = [
    ("福岡", ["福岡県", "福岡市"]),
    ("大阪", ["大阪府", "大阪市"]),
    ("京都", ["京都府", "京都市"]),
    ("千葉", ["千葉県", "千葉市"]),
    ("広島", ["広島県", "広島市"]),
    ("静岡", ["静岡県", "静岡市"]),
    ("新潟", ["新潟県", "新潟市"]),
    ("岡山", ["岡山県", "岡山市"]),
    ("熊本", ["熊本県", "熊本市"]),
]


class TestAmbiguousAreaPatterns:
    @pytest.mark.parametrize("query,expected_candidates", AMBIGUOUS_PATTERNS)
    def test_all_ambiguous_patterns(self, query, expected_candidates):
        with pytest.raises(AmbiguousAreaError) as exc_info:
            _resolve_single_area(query)
        msg = str(exc_info.value)
        for candidate in expected_candidates:
            assert candidate in msg


# ------------------------------------------------------------------
# ツール登録の確認
# ------------------------------------------------------------------


class TestToolRegistration:
    def test_all_tools_registered(self):
        tool_names = set(mcp._tool_manager._tools.keys())
        expected = {
            "search_statistics",
            "get_regional_data",
            "compare_regions",
            "resolve_area",
            "list_available_stats",
            "get_meta_info",
            "get_population",
            "get_regional_profile",
            "search_corporations",
            "get_corporation",
            "get_real_estate_transactions",
            "check_invoice_registration",
            "validate_invoice_on_date",
            "search_invoice_by_name",
        }
        assert expected == tool_names

    def test_search_statistics_has_description(self):
        tool = mcp._tool_manager._tools["search_statistics"]
        assert "キーワード" in tool.description
        assert "統計表" in tool.description

    def test_compare_regions_has_description(self):
        tool = mcp._tool_manager._tools["compare_regions"]
        assert "比較" in tool.description


# ------------------------------------------------------------------
# ツールの実行テスト（EStatClient をモック）
# ------------------------------------------------------------------


def _make_mock_ctx(
    client: object,
    *,
    corp_client: object | None = None,
    realestate_client: object | None = None,
    invoice_client: object | None = None,
) -> MagicMock:
    """Context のモックを生成."""
    ctx = MagicMock()
    ctx.fastmcp = MagicMock()
    ctx.fastmcp._estat_client = client
    ctx.fastmcp._corp_client = corp_client
    ctx.fastmcp._realestate_client = realestate_client
    ctx.fastmcp._invoice_client = invoice_client
    ctx.info = AsyncMock()
    return ctx


def _sample_tables() -> list[TableInfo]:
    return [
        TableInfo(
            id="0003448237",
            stat_name="国勢調査",
            gov_org="総務省",
            title="男女別人口",
            survey_date="202001",
        ),
    ]


def _sample_stats_data() -> StatsData:
    meta = MetaInfo(
        table_id="0003448237",
        class_objects=[
            ClassObject(
                id="tab",
                name="表章項目",
                items=[ClassItem(code="001", name="人口", unit="人")],
            ),
            ClassObject(
                id="area",
                name="地域",
                items=[
                    ClassItem(code="13000", name="東京都"),
                    ClassItem(code="27000", name="大阪府"),
                ],
            ),
            ClassObject(
                id="time",
                name="時間軸",
                items=[
                    ClassItem(code="2020000000", name="2020年"),
                    ClassItem(code="2015000000", name="2015年"),
                ],
            ),
        ],
    )
    return StatsData(
        table_id="0003448237",
        meta_info=meta,
        values=[
            DataValue(
                value="13960000",
                dimensions={"tab": "001", "area": "13000", "time": "2020000000"},
            ),
            DataValue(
                value="8838000",
                dimensions={"tab": "001", "area": "27000", "time": "2020000000"},
            ),
            DataValue(
                value="13515000",
                dimensions={"tab": "001", "area": "13000", "time": "2015000000"},
            ),
            DataValue(
                value="8839000",
                dimensions={"tab": "001", "area": "27000", "time": "2015000000"},
            ),
        ],
        total_count=4,
    )


class TestSearchStatistics:
    async def test_returns_formatted_results(self):
        mock_client = MagicMock()
        mock_client.search_stats = AsyncMock(return_value=_sample_tables())
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import search_statistics

        result = await search_statistics("人口", ctx)

        assert "国勢調査" in result
        assert "0003448237" in result
        assert "男女別人口" in result
        mock_client.search_stats.assert_called_once()

    async def test_no_results(self):
        mock_client = MagicMock()
        mock_client.search_stats = AsyncMock(return_value=[])
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import search_statistics

        result = await search_statistics("存在しないキーワード", ctx)
        assert "見つかりませんでした" in result


class TestGetRegionalData:
    async def test_returns_markdown_table(self):
        mock_client = MagicMock()
        mock_client.get_stats_data = AsyncMock(return_value=_sample_stats_data())
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_regional_data

        result = await get_regional_data("0003448237", "東京都", ctx)

        assert "13,960,000" in result
        assert "東京都" in result
        assert "|" in result  # markdown table

    async def test_empty_data(self):
        empty_data = StatsData(
            table_id="TEST",
            meta_info=MetaInfo(table_id="TEST", class_objects=[]),
            values=[],
        )
        mock_client = MagicMock()
        mock_client.get_stats_data = AsyncMock(return_value=empty_data)
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_regional_data

        result = await get_regional_data("TEST", "東京都", ctx)
        assert "見つかりませんでした" in result


class TestCompareRegions:
    async def test_returns_pivot_table(self):
        mock_client = MagicMock()
        mock_client.get_stats_data = AsyncMock(return_value=_sample_stats_data())
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import compare_regions

        result = await compare_regions(
            "0003448237", ["東京都", "大阪府"], ctx
        )

        assert "東京都" in result
        assert "大阪府" in result
        assert "2020年" in result
        # ピボットテーブルには時間軸ヘッダーがある
        assert "時間軸" in result

    async def test_area_codes_joined(self):
        mock_client = MagicMock()
        mock_client.get_stats_data = AsyncMock(return_value=_sample_stats_data())
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import compare_regions

        await compare_regions("0003448237", ["東京都", "大阪府"], ctx)

        call_kwargs = mock_client.get_stats_data.call_args
        # cd_area に "13000,27000" が渡されている
        assert call_kwargs.kwargs.get("cd_area") == "13000,27000"


class TestResolveArea:
    async def test_exact_match(self):
        from japan_data_mcp.server import resolve_area

        result = await resolve_area("東京都")
        assert "13000" in result
        assert "東京都" in result

    async def test_partial_match(self):
        from japan_data_mcp.server import resolve_area

        result = await resolve_area("東京")
        assert "13000" in result

    async def test_no_match(self):
        from japan_data_mcp.server import resolve_area

        result = await resolve_area("アトランティス")
        assert "見つかりませんでした" in result


class TestListAvailableStats:
    async def test_returns_all_fields(self):
        from japan_data_mcp.server import list_available_stats

        result = await list_available_stats()
        assert "人口・世帯" in result
        assert "02" in result
        assert "統計分野一覧" in result


class TestGetMetaInfo:
    async def test_returns_class_objects(self):
        sample_meta = _sample_stats_data().meta_info
        mock_client = MagicMock()
        mock_client.get_meta_info = AsyncMock(return_value=sample_meta)
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_meta_info

        result = await get_meta_info("0003448237", ctx)

        assert "表章項目" in result
        assert "地域" in result
        assert "時間軸" in result
        assert "人口" in result
        assert "東京都" in result


# ------------------------------------------------------------------
# 曖昧地域名のツール実行テスト
# ------------------------------------------------------------------


class TestAmbiguousAreaInTools:
    """曖昧な地域名を渡した場合、各ツールがエラー文字列を返しAPIを呼ばないことを確認."""

    async def test_get_regional_data_ambiguous(self):
        mock_client = MagicMock()
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_regional_data

        result = await get_regional_data("0003448237", "静岡", ctx)

        assert "静岡県" in result
        assert "静岡市" in result
        assert "複数の地域に一致" in result
        mock_client.get_stats_data.assert_not_called()

    async def test_compare_regions_ambiguous(self):
        mock_client = MagicMock()
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import compare_regions

        result = await compare_regions(
            "0003448237", ["東京都", "福岡"], ctx
        )

        assert "福岡県" in result
        assert "福岡市" in result
        assert "複数の地域に一致" in result
        mock_client.get_stats_data.assert_not_called()

    async def test_get_population_ambiguous(self):
        mock_client = MagicMock()
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_population

        result = await get_population("大阪", ctx)

        assert "大阪府" in result
        assert "大阪市" in result
        assert "複数の地域に一致" in result

    async def test_get_regional_profile_ambiguous(self):
        mock_client = MagicMock()
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_regional_profile

        result = await get_regional_profile("京都", ctx)

        assert "京都府" in result
        assert "京都市" in result
        assert "複数の地域に一致" in result


# ------------------------------------------------------------------
# 対応1: 市区町村コード解決のテスト
# ------------------------------------------------------------------


class TestMunicipalityResolution:
    """全国市区町村の地域名解決テスト."""

    def test_mito_city(self):
        assert _resolve_single_area("水戸市") == "08201"

    def test_mito_partial(self):
        """「水戸」で水戸市にマッチする."""
        assert _resolve_single_area("水戸") == "08201"

    def test_utsunomiya_city(self):
        assert _resolve_single_area("宇都宮市") == "09201"

    def test_maebashi_city(self):
        assert _resolve_single_area("前橋市") == "10201"

    def test_fuchu_ambiguous(self):
        """「府中」は東京都府中市と広島県府中市で曖昧."""
        with pytest.raises(AmbiguousAreaError) as exc_info:
            _resolve_single_area("府中")
        msg = str(exc_info.value)
        assert "府中市（東京都）" in msg
        assert "府中市（広島県）" in msg

    def test_fuchu_exact(self):
        """都道府県名付きなら一意に解決."""
        assert _resolve_single_area("府中市（東京都）") == "13206"
        assert _resolve_single_area("府中市（広島県）") == "34208"

    def test_existing_designated_cities_still_work(self):
        """既存の政令指定都市も引き続き動作."""
        assert _resolve_single_area("横浜市") == "14100"
        assert _resolve_single_area("名古屋市") == "23100"

    def test_existing_prefectures_still_work(self):
        """既存の都道府県も引き続き動作."""
        assert _resolve_single_area("東京都") == "13000"
        assert _resolve_single_area("茨城県") == "08000"


# ------------------------------------------------------------------
# 対応2: compare_regions で市区町村間比較
# ------------------------------------------------------------------


class TestCompareRegionsMunicipalities:
    """市区町村間の compare_regions テスト."""

    async def test_mito_utsunomiya_maebashi(self):
        mock_client = MagicMock()
        mock_client.get_stats_data = AsyncMock(return_value=_sample_stats_data())
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import compare_regions

        await compare_regions(
            "0003448237", ["水戸市", "宇都宮市", "前橋市"], ctx
        )

        call_kwargs = mock_client.get_stats_data.call_args
        # 市区町村コードが正しく結合されている
        assert call_kwargs.kwargs.get("cd_area") == "08201,09201,10201"


# ------------------------------------------------------------------
# 対応3: summary=True のテスト
# ------------------------------------------------------------------


def _sample_stats_data_multi_time() -> StatsData:
    """複数時点のデータを含むサンプル."""
    meta = MetaInfo(
        table_id="0003448237",
        class_objects=[
            ClassObject(
                id="tab",
                name="表章項目",
                items=[
                    ClassItem(code="001", name="人口", unit="人"),
                    ClassItem(code="002", name="世帯数", unit="世帯"),
                ],
            ),
            ClassObject(
                id="area",
                name="地域",
                items=[ClassItem(code="13000", name="東京都")],
            ),
            ClassObject(
                id="time",
                name="時間軸",
                items=[
                    ClassItem(code="2020000000", name="2020年"),
                    ClassItem(code="2015000000", name="2015年"),
                    ClassItem(code="2010000000", name="2010年"),
                ],
            ),
        ],
    )
    values = [
        DataValue(
            value="13960000",
            dimensions={"tab": "001", "area": "13000", "time": "2020000000"},
        ),
        DataValue(
            value="7000000",
            dimensions={"tab": "002", "area": "13000", "time": "2020000000"},
        ),
        DataValue(
            value="13515000",
            dimensions={"tab": "001", "area": "13000", "time": "2015000000"},
        ),
        DataValue(
            value="6690000",
            dimensions={"tab": "002", "area": "13000", "time": "2015000000"},
        ),
        DataValue(
            value="13159000",
            dimensions={"tab": "001", "area": "13000", "time": "2010000000"},
        ),
        DataValue(
            value="6390000",
            dimensions={"tab": "002", "area": "13000", "time": "2010000000"},
        ),
    ]
    return StatsData(
        table_id="0003448237", meta_info=meta, values=values, total_count=6
    )


class TestGetRegionalDataSummary:
    """summary=True のテスト."""

    async def test_summary_filters_to_latest_time(self):
        mock_client = MagicMock()
        mock_client.get_stats_data = AsyncMock(
            return_value=_sample_stats_data_multi_time()
        )
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_regional_data

        result = await get_regional_data(
            "0003448237", "東京都", ctx, summary=True
        )

        # 最新年（2020年）のデータのみ表示
        assert "2020年" in result
        assert "13,960,000" in result
        # 2015年、2010年のデータは含まれない
        assert "2015年" not in result
        assert "2010年" not in result

    async def test_summary_false_returns_all(self):
        mock_client = MagicMock()
        mock_client.get_stats_data = AsyncMock(
            return_value=_sample_stats_data_multi_time()
        )
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_regional_data

        result = await get_regional_data(
            "0003448237", "東京都", ctx, summary=False
        )

        # 全時点のデータが含まれる
        assert "2020年" in result
        assert "2015年" in result
        assert "2010年" in result

    async def test_summary_note_in_header(self):
        mock_client = MagicMock()
        mock_client.get_stats_data = AsyncMock(
            return_value=_sample_stats_data_multi_time()
        )
        ctx = _make_mock_ctx(mock_client)

        from japan_data_mcp.server import get_regional_data

        result = await get_regional_data(
            "0003448237", "東京都", ctx, summary=True
        )

        # サマリーモードの注記が含まれる
        assert "のデータのみ表示" in result


# ------------------------------------------------------------------
# 法人番号ツールのテスト
# ------------------------------------------------------------------


def _sample_corporations() -> list[Corporation]:
    return [
        Corporation(
            corporate_number="2180001011843",
            name="トヨタ自動車株式会社",
            kind="301",
            prefecture_name="愛知県",
            city_name="豊田市",
            street_number="トヨタ町1番地",
            post_code="4711195",
            prefecture_code="23",
            city_code="211",
            assignment_date="2015-10-05",
            update_date="2023-04-01",
            change_date="2023-04-01",
            furigana="トヨタジドウシャ",
        ),
    ]


class TestSearchCorporations:
    async def test_returns_formatted_table(self):
        mock_corp_client = MagicMock()
        mock_corp_client.search_by_name = AsyncMock(
            return_value=_sample_corporations()
        )
        ctx = _make_mock_ctx(MagicMock(), corp_client=mock_corp_client)

        from japan_data_mcp.server import search_corporations

        result = await search_corporations("トヨタ", ctx)

        assert "トヨタ自動車株式会社" in result
        assert "2180001011843" in result
        assert "愛知県" in result
        assert "データ検証情報" in result
        assert "法人番号公表サイト" in result

    async def test_no_results(self):
        mock_corp_client = MagicMock()
        mock_corp_client.search_by_name = AsyncMock(return_value=[])
        ctx = _make_mock_ctx(MagicMock(), corp_client=mock_corp_client)

        from japan_data_mcp.server import search_corporations

        result = await search_corporations("存在しない法人名", ctx)
        assert "見つかりませんでした" in result

    async def test_not_configured(self):
        ctx = _make_mock_ctx(MagicMock(), corp_client=None)

        from japan_data_mcp.server import search_corporations

        result = await search_corporations("テスト", ctx)
        assert "CORP_APP_ID" in result

    async def test_area_filter(self):
        mock_corp_client = MagicMock()
        mock_corp_client.search_by_name = AsyncMock(
            return_value=_sample_corporations()
        )
        ctx = _make_mock_ctx(MagicMock(), corp_client=mock_corp_client)

        from japan_data_mcp.server import search_corporations

        await search_corporations("トヨタ", ctx, area="愛知県")

        call_kwargs = mock_corp_client.search_by_name.call_args
        assert call_kwargs.kwargs.get("prefecture_code") == "23"

    async def test_api_error(self):
        mock_corp_client = MagicMock()
        mock_corp_client.search_by_name = AsyncMock(
            side_effect=CorpApiError(400, "検索条件が不正です")
        )
        ctx = _make_mock_ctx(MagicMock(), corp_client=mock_corp_client)

        from japan_data_mcp.server import search_corporations

        result = await search_corporations("テスト", ctx)
        assert "エラー" in result


class TestGetCorporation:
    async def test_returns_detail(self):
        mock_corp_client = MagicMock()
        mock_corp_client.get_by_number = AsyncMock(
            return_value=_sample_corporations()
        )
        ctx = _make_mock_ctx(MagicMock(), corp_client=mock_corp_client)

        from japan_data_mcp.server import get_corporation

        result = await get_corporation("2180001011843", ctx)

        assert "トヨタ自動車株式会社" in result
        assert "株式会社" in result
        assert "愛知県豊田市" in result
        assert "データ検証情報" in result

    async def test_not_found(self):
        mock_corp_client = MagicMock()
        mock_corp_client.get_by_number = AsyncMock(return_value=[])
        ctx = _make_mock_ctx(MagicMock(), corp_client=mock_corp_client)

        from japan_data_mcp.server import get_corporation

        result = await get_corporation("0000000000000", ctx)
        assert "見つかりませんでした" in result

    async def test_not_configured(self):
        ctx = _make_mock_ctx(MagicMock(), corp_client=None)

        from japan_data_mcp.server import get_corporation

        result = await get_corporation("2180001011843", ctx)
        assert "CORP_APP_ID" in result


# ------------------------------------------------------------------
# 不動産取引価格ツールのテスト
# ------------------------------------------------------------------


def _sample_transactions() -> list[Transaction]:
    return [
        Transaction(
            transaction_type="宅地(土地と建物)",
            trade_price="35000000",
            area="100",
            municipality_code="08201",
            prefecture="茨城県",
            municipality="水戸市",
            district_name="笠原町",
            region="住宅地",
            building_year="2010年",
            period="第１四半期",
        ),
        Transaction(
            transaction_type="中古マンション等",
            trade_price="18000000",
            area="70",
            municipality_code="08201",
            prefecture="茨城県",
            municipality="水戸市",
            district_name="宮町",
            region="商業地",
            building_year="2005年",
            period="第２四半期",
        ),
    ]


class TestGetRealEstateTransactions:
    async def test_returns_formatted_report(self):
        mock_re_client = MagicMock()
        mock_re_client.get_transactions = AsyncMock(
            return_value=_sample_transactions()
        )
        ctx = _make_mock_ctx(MagicMock(), realestate_client=mock_re_client)

        from japan_data_mcp.server import get_real_estate_transactions

        result = await get_real_estate_transactions("水戸市", ctx)

        assert "不動産取引価格情報" in result
        assert "水戸市" in result or "笠原町" in result
        assert "3,500万円" in result
        assert "データ検証情報" in result
        assert "不動産情報ライブラリ" in result

    async def test_no_results(self):
        mock_re_client = MagicMock()
        mock_re_client.get_transactions = AsyncMock(return_value=[])
        ctx = _make_mock_ctx(MagicMock(), realestate_client=mock_re_client)

        from japan_data_mcp.server import get_real_estate_transactions

        result = await get_real_estate_transactions("水戸市", ctx)
        assert "見つかりませんでした" in result

    async def test_not_configured(self):
        ctx = _make_mock_ctx(MagicMock(), realestate_client=None)

        from japan_data_mcp.server import get_real_estate_transactions

        result = await get_real_estate_transactions("水戸市", ctx)
        assert "REALESTATE_API_KEY" in result

    async def test_prefecture_code_extraction(self):
        mock_re_client = MagicMock()
        mock_re_client.get_transactions = AsyncMock(
            return_value=_sample_transactions()
        )
        ctx = _make_mock_ctx(MagicMock(), realestate_client=mock_re_client)

        from japan_data_mcp.server import get_real_estate_transactions

        await get_real_estate_transactions("水戸市", ctx)

        call_args = mock_re_client.get_transactions.call_args
        # 都道府県コード（上2桁）が渡されている
        assert call_args.args[0] == "08"
        # 市区町村コードも渡されている
        assert call_args.kwargs.get("city_code") == "08201"

    async def test_prefecture_level(self):
        """都道府県レベルでは city_code を渡さない."""
        mock_re_client = MagicMock()
        mock_re_client.get_transactions = AsyncMock(
            return_value=_sample_transactions()
        )
        ctx = _make_mock_ctx(MagicMock(), realestate_client=mock_re_client)

        from japan_data_mcp.server import get_real_estate_transactions

        await get_real_estate_transactions("茨城県", ctx)

        call_args = mock_re_client.get_transactions.call_args
        assert call_args.args[0] == "08"
        assert call_args.kwargs.get("city_code") is None

    async def test_year_passed_through(self):
        mock_re_client = MagicMock()
        mock_re_client.get_transactions = AsyncMock(return_value=[])
        ctx = _make_mock_ctx(MagicMock(), realestate_client=mock_re_client)

        from japan_data_mcp.server import get_real_estate_transactions

        await get_real_estate_transactions("水戸市", ctx, year=2023)

        call_args = mock_re_client.get_transactions.call_args
        assert call_args.kwargs.get("year") == 2023


# ------------------------------------------------------------------
# インボイスツールのテスト
# ------------------------------------------------------------------


def _sample_issuers() -> list[InvoiceIssuer]:
    return [
        InvoiceIssuer(
            registrated_number="T2180001011843",
            name="トヨタ自動車株式会社",
            kind="2",
            process="01",
            registration_date="2023-10-01",
            update_date="2023-09-15",
            address="愛知県豊田市トヨタ町１番地",
            address_prefecture_code="23",
        ),
    ]


class TestCheckInvoiceRegistration:
    async def test_returns_detail(self):
        mock_invoice_client = MagicMock()
        mock_invoice_client.get_by_number = AsyncMock(
            return_value=_sample_issuers()
        )
        ctx = _make_mock_ctx(
            MagicMock(), invoice_client=mock_invoice_client
        )

        from japan_data_mcp.server import check_invoice_registration

        result = await check_invoice_registration("T2180001011843", ctx)

        assert "トヨタ自動車株式会社" in result
        assert "T2180001011843" in result
        assert "登録中" in result
        assert "データ検証情報" in result

    async def test_not_found(self):
        mock_invoice_client = MagicMock()
        mock_invoice_client.get_by_number = AsyncMock(return_value=[])
        ctx = _make_mock_ctx(
            MagicMock(), invoice_client=mock_invoice_client
        )

        from japan_data_mcp.server import check_invoice_registration

        result = await check_invoice_registration("T0000000000000", ctx)
        assert "見つかりませんでした" in result

    async def test_not_configured(self):
        ctx = _make_mock_ctx(MagicMock(), invoice_client=None)

        from japan_data_mcp.server import check_invoice_registration

        result = await check_invoice_registration("T2180001011843", ctx)
        assert "CORP_APP_ID" in result

    async def test_invalid_number(self):
        mock_invoice_client = MagicMock()
        ctx = _make_mock_ctx(
            MagicMock(), invoice_client=mock_invoice_client
        )

        from japan_data_mcp.server import check_invoice_registration

        result = await check_invoice_registration("INVALID", ctx)
        assert "形式が不正" in result


class TestSearchInvoiceByName:
    async def test_returns_combined_table(self):
        mock_corp_client = MagicMock()
        mock_corp_client.search_by_name = AsyncMock(
            return_value=_sample_corporations()
        )
        mock_invoice_client = MagicMock()
        mock_invoice_client.get_by_number = AsyncMock(
            return_value=_sample_issuers()
        )
        ctx = _make_mock_ctx(
            MagicMock(),
            corp_client=mock_corp_client,
            invoice_client=mock_invoice_client,
        )

        from japan_data_mcp.server import search_invoice_by_name

        result = await search_invoice_by_name("トヨタ", ctx)

        assert "トヨタ自動車株式会社" in result
        assert "T2180001011843" in result
        assert "登録中" in result
        assert "データ検証情報" in result

    async def test_corp_found_but_not_registered(self):
        mock_corp_client = MagicMock()
        mock_corp_client.search_by_name = AsyncMock(
            return_value=_sample_corporations()
        )
        mock_invoice_client = MagicMock()
        mock_invoice_client.get_by_number = AsyncMock(return_value=[])
        ctx = _make_mock_ctx(
            MagicMock(),
            corp_client=mock_corp_client,
            invoice_client=mock_invoice_client,
        )

        from japan_data_mcp.server import search_invoice_by_name

        result = await search_invoice_by_name("トヨタ", ctx)

        assert "トヨタ自動車株式会社" in result
        assert "未登録" in result

    async def test_no_corps_found(self):
        mock_corp_client = MagicMock()
        mock_corp_client.search_by_name = AsyncMock(return_value=[])
        mock_invoice_client = MagicMock()
        ctx = _make_mock_ctx(
            MagicMock(),
            corp_client=mock_corp_client,
            invoice_client=mock_invoice_client,
        )

        from japan_data_mcp.server import search_invoice_by_name

        result = await search_invoice_by_name("存在しない法人名", ctx)

        assert "見つかりませんでした" in result
        assert "個人事業主" in result

    async def test_not_configured(self):
        ctx = _make_mock_ctx(MagicMock(), corp_client=None, invoice_client=None)

        from japan_data_mcp.server import search_invoice_by_name

        result = await search_invoice_by_name("テスト", ctx)
        assert "CORP_APP_ID" in result

    async def test_area_filter(self):
        mock_corp_client = MagicMock()
        mock_corp_client.search_by_name = AsyncMock(
            return_value=_sample_corporations()
        )
        mock_invoice_client = MagicMock()
        mock_invoice_client.get_by_number = AsyncMock(
            return_value=_sample_issuers()
        )
        ctx = _make_mock_ctx(
            MagicMock(),
            corp_client=mock_corp_client,
            invoice_client=mock_invoice_client,
        )

        from japan_data_mcp.server import search_invoice_by_name

        await search_invoice_by_name("トヨタ", ctx, area="愛知県")

        call_kwargs = mock_corp_client.search_by_name.call_args
        assert call_kwargs.kwargs.get("prefecture_code") == "23"
