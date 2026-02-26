"""プリセットツールのユニットテスト."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from japan_data_mcp.estat.models import (
    ClassItem,
    ClassObject,
    DataValue,
    EStatApiError,
    MetaInfo,
    StatsData,
    TableInfo,
)
from japan_data_mcp.presets.population import (
    SearchSpec,
    fetch_population,
    fetch_section,
    format_section,
    select_table,
)
from japan_data_mcp.presets.regional import fetch_regional_profile


# ------------------------------------------------------------------
# テスト用データファクトリ
# ------------------------------------------------------------------


def _make_table(
    table_id: str = "TEST001",
    title: str = "テスト統計表",
    stat_name: str = "テスト調査",
    survey_date: str = "202001",
    small_area: bool = False,
) -> TableInfo:
    return TableInfo(
        id=table_id,
        stat_name=stat_name,
        gov_org="総務省",
        title=title,
        survey_date=survey_date,
        small_area=small_area,
    )


def _make_stats_data(
    table_id: str = "TEST001",
    area_code: str = "13000",
    area_name: str = "東京都",
) -> StatsData:
    meta = MetaInfo(
        table_id=table_id,
        class_objects=[
            ClassObject(
                id="tab",
                name="表章項目",
                items=[ClassItem(code="001", name="人口", unit="人")],
            ),
            ClassObject(
                id="area",
                name="地域",
                items=[ClassItem(code=area_code, name=area_name)],
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
        table_id=table_id,
        meta_info=meta,
        values=[
            DataValue(
                value="13960000",
                dimensions={"tab": "001", "area": area_code, "time": "2020000000"},
            ),
            DataValue(
                value="13515000",
                dimensions={"tab": "001", "area": area_code, "time": "2015000000"},
            ),
        ],
        total_count=2,
    )


def _make_empty_stats_data(table_id: str = "EMPTY") -> StatsData:
    return StatsData(
        table_id=table_id,
        meta_info=MetaInfo(table_id=table_id, class_objects=[]),
        values=[],
    )


def _make_mock_client(
    search_result: list[TableInfo] | None = None,
    stats_data: StatsData | None = None,
    search_error: bool = False,
    data_error: bool = False,
) -> MagicMock:
    client = MagicMock()

    if search_error:
        client.search_stats = AsyncMock(
            side_effect=EStatApiError(100, "検索エラー")
        )
    else:
        client.search_stats = AsyncMock(
            return_value=search_result or []
        )

    if data_error:
        client.get_stats_data = AsyncMock(
            side_effect=EStatApiError(100, "データ取得エラー")
        )
    else:
        client.get_stats_data = AsyncMock(
            return_value=stats_data or _make_empty_stats_data()
        )

    return client


# ------------------------------------------------------------------
# select_table
# ------------------------------------------------------------------


class TestSelectTable:
    def test_returns_none_for_empty(self):
        assert select_table([]) is None

    def test_prefers_non_small_area(self):
        tables = [
            _make_table(table_id="SMALL", small_area=True, survey_date="202001"),
            _make_table(table_id="NORMAL", small_area=False, survey_date="201501"),
        ]
        selected = select_table(tables)
        assert selected is not None
        assert selected.id == "NORMAL"

    def test_prefers_newer_survey_date(self):
        tables = [
            _make_table(table_id="OLD", survey_date="201501"),
            _make_table(table_id="NEW", survey_date="202001"),
        ]
        selected = select_table(tables)
        assert selected is not None
        assert selected.id == "NEW"

    def test_falls_back_to_small_area_if_only_option(self):
        tables = [_make_table(table_id="SMALL", small_area=True)]
        selected = select_table(tables)
        assert selected is not None
        assert selected.id == "SMALL"


# ------------------------------------------------------------------
# fetch_section
# ------------------------------------------------------------------


class TestFetchSection:
    async def test_success(self):
        table = _make_table()
        data = _make_stats_data()
        client = _make_mock_client(
            search_result=[table], stats_data=data
        )
        spec = SearchSpec(
            label="テスト", keyword="人口", stats_code="00200521"
        )

        label, result_data, result_table = await fetch_section(
            client, spec, "13000"
        )

        assert label == "テスト"
        assert result_data is not None
        assert len(result_data.values) == 2
        assert result_table is not None
        assert result_table.id == "TEST001"

    async def test_search_returns_empty(self):
        client = _make_mock_client(search_result=[])
        spec = SearchSpec(
            label="テスト", keyword="存在しない", stats_code="99999999"
        )

        label, data, table = await fetch_section(client, spec, "13000")

        assert data is None
        assert table is None

    async def test_search_api_error(self):
        client = _make_mock_client(search_error=True)
        spec = SearchSpec(
            label="テスト", keyword="人口", stats_code="00200521"
        )

        label, data, table = await fetch_section(client, spec, "13000")

        assert data is None
        assert table is None

    async def test_data_fetch_error(self):
        table = _make_table()
        client = _make_mock_client(
            search_result=[table], data_error=True
        )
        spec = SearchSpec(
            label="テスト", keyword="人口", stats_code="00200521"
        )

        label, data, table_result = await fetch_section(
            client, spec, "13000"
        )

        assert data is None
        # テーブルは見つかっている
        assert table_result is not None


# ------------------------------------------------------------------
# format_section
# ------------------------------------------------------------------


class TestFormatSection:
    def test_basic_format(self):
        data = _make_stats_data()
        table = _make_table(title="男女別人口", stat_name="国勢調査")

        result = format_section("人口推移", data, table)

        assert "### 人口推移" in result
        assert "国勢調査" in result
        assert "男女別人口" in result
        assert "13,960,000" in result

    def test_exclude_dims(self):
        data = _make_stats_data()
        table = _make_table()

        result = format_section(
            "テスト", data, table, exclude_dims={"地域"}
        )

        assert "東京都" not in result.split("\n")[3]  # テーブル行に地域が出ない

    def test_without_table_info(self):
        data = _make_stats_data()
        result = format_section("テスト", data, None)

        assert "### テスト" in result
        assert "出典" not in result


# ------------------------------------------------------------------
# fetch_population
# ------------------------------------------------------------------


class TestFetchPopulation:
    async def test_success(self):
        table = _make_table(stat_name="人口推計", title="都道府県別人口")
        data = _make_stats_data()
        client = _make_mock_client(
            search_result=[table], stats_data=data
        )

        result = await fetch_population(client, "13000", "東京都")

        assert "東京都 の人口データ" in result
        assert "13,960,000" in result
        assert "人口推計" in result
        assert "TEST001" in result

    async def test_no_data_found(self):
        client = _make_mock_client(search_result=[])

        result = await fetch_population(client, "13000", "東京都")

        assert "見つかりませんでした" in result
        assert "search_statistics" in result

    async def test_tries_fallback_source(self):
        """最初のソースが失敗しても2番目で取得できる."""
        table = _make_table(stat_name="国勢調査", title="男女別人口")
        data = _make_stats_data()

        call_count = 0

        async def mock_search(keyword, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # 最初のソースは空
            return [table]

        client = MagicMock()
        client.search_stats = AsyncMock(side_effect=mock_search)
        client.get_stats_data = AsyncMock(return_value=data)

        result = await fetch_population(client, "13000", "東京都")

        assert "国勢調査" in result
        assert "13,960,000" in result
        assert call_count == 2

    async def test_empty_values_skipped(self):
        """テーブルは見つかるがデータが空の場合、次のソースへ."""
        table = _make_table()
        empty_data = _make_empty_stats_data()

        client = _make_mock_client(
            search_result=[table], stats_data=empty_data
        )

        result = await fetch_population(client, "13000", "東京都")

        assert "見つかりませんでした" in result


# ------------------------------------------------------------------
# fetch_regional_profile
# ------------------------------------------------------------------


class TestFetchRegionalProfile:
    async def test_success_all_sections(self):
        """全セクション取得成功."""
        table = _make_table()
        data = _make_stats_data()
        client = _make_mock_client(
            search_result=[table], stats_data=data
        )

        result = await fetch_regional_profile(client, "13000", "東京都")

        assert "東京都 の地域プロファイル" in result
        assert "13,960,000" in result
        # フッター
        assert "search_statistics" in result

    async def test_partial_failure(self):
        """一部セクションが失敗しても他は表示される."""
        table = _make_table()
        data = _make_stats_data()

        call_count = 0

        async def mock_search(keyword, **kwargs):
            nonlocal call_count
            call_count += 1
            # 人口は成功、経済と労働は失敗
            if "人口" in keyword:
                return [table]
            return []

        client = MagicMock()
        client.search_stats = AsyncMock(side_effect=mock_search)
        client.get_stats_data = AsyncMock(return_value=data)

        result = await fetch_regional_profile(client, "13000", "東京都")

        # 人口セクションは表示される
        assert "13,960,000" in result
        # 取得できなかったセクションのメッセージ
        assert "取得できませんでした" in result

    async def test_all_sections_fail(self):
        """全セクション失敗."""
        client = _make_mock_client(search_result=[])

        result = await fetch_regional_profile(client, "13000", "東京都")

        assert "見つかりませんでした" in result


# ------------------------------------------------------------------
# server.py のプリセットツール登録テスト
# ------------------------------------------------------------------


class TestPresetToolRegistration:
    def test_get_population_registered(self):
        from japan_data_mcp.server import mcp

        assert "get_population" in mcp._tool_manager._tools
        tool = mcp._tool_manager._tools["get_population"]
        assert "人口" in tool.description

    def test_get_regional_profile_registered(self):
        from japan_data_mcp.server import mcp

        assert "get_regional_profile" in mcp._tool_manager._tools
        tool = mcp._tool_manager._tools["get_regional_profile"]
        assert "プロファイル" in tool.description


class TestPresetToolExecution:
    async def test_get_population_tool(self):
        from japan_data_mcp.server import get_population

        table = _make_table(stat_name="人口推計", title="都道府県別人口")
        data = _make_stats_data()
        mock_client = _make_mock_client(
            search_result=[table], stats_data=data
        )

        ctx = MagicMock()
        ctx.fastmcp = MagicMock()
        ctx.fastmcp._estat_client = mock_client
        ctx.info = AsyncMock()

        result = await get_population("東京都", ctx)

        assert "東京都" in result
        assert "13,960,000" in result

    async def test_get_regional_profile_tool(self):
        from japan_data_mcp.server import get_regional_profile

        table = _make_table()
        data = _make_stats_data()
        mock_client = _make_mock_client(
            search_result=[table], stats_data=data
        )

        ctx = MagicMock()
        ctx.fastmcp = MagicMock()
        ctx.fastmcp._estat_client = mock_client
        ctx.info = AsyncMock()

        result = await get_regional_profile("東京", ctx)

        assert "東京都" in result

    async def test_get_population_with_code(self):
        """地域コードで指定した場合も動作する."""
        from japan_data_mcp.server import get_population

        table = _make_table()
        data = _make_stats_data()
        mock_client = _make_mock_client(
            search_result=[table], stats_data=data
        )

        ctx = MagicMock()
        ctx.fastmcp = MagicMock()
        ctx.fastmcp._estat_client = mock_client
        ctx.info = AsyncMock()

        result = await get_population("13000", ctx)

        # コードから逆引きで「東京都」が表示される
        assert "東京都" in result
