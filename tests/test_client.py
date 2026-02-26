"""EStatClient のユニットテスト."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from japan_data_mcp.estat.client import EStatClient
from japan_data_mcp.estat.models import EStatApiError


# ------------------------------------------------------------------
# フィクスチャ
# ------------------------------------------------------------------


@pytest.fixture
def client():
    return EStatClient(app_id="test_app_id")


def _mock_response(body: dict) -> httpx.Response:
    """httpx.Response のモックを生成."""
    return httpx.Response(
        status_code=200,
        json=body,
        request=httpx.Request("GET", "https://example.com"),
    )


# ------------------------------------------------------------------
# 初期化
# ------------------------------------------------------------------


class TestInit:
    def test_app_id_from_argument(self):
        c = EStatClient(app_id="my_key")
        assert c._app_id == "my_key"

    def test_missing_app_id_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ESTAT_APP_ID"):
                EStatClient(app_id="")


# ------------------------------------------------------------------
# search_stats
# ------------------------------------------------------------------


SEARCH_RESPONSE = {
    "GET_STATS_LIST": {
        "RESULT": {"STATUS": 0, "ERROR_MSG": "正常に終了しました。"},
        "DATALIST_INF": {
            "NUMBER": 1,
            "TABLE_INF": [
                {
                    "@id": "0003448237",
                    "STAT_NAME": {"@code": "00200521", "$": "国勢調査"},
                    "GOV_ORG": {"@code": "00200", "$": "総務省"},
                    "TITLE": {"$": "男女別人口"},
                    "SURVEY_DATE": "202001",
                    "OPEN_DATE": "2022-03-25",
                    "SMALL_AREA": 0,
                }
            ],
        },
    }
}


class TestSearchStats:
    @pytest.mark.asyncio
    async def test_basic_search(self, client):
        mock_resp = _mock_response(SEARCH_RESPONSE)
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with client:
                tables = await client.search_stats("人口")

        assert len(tables) == 1
        t = tables[0]
        assert t.id == "0003448237"
        assert t.stat_name == "国勢調査"
        assert t.gov_org == "総務省"
        assert t.title == "男女別人口"
        assert t.small_area is False

    @pytest.mark.asyncio
    async def test_single_table_as_dict(self, client):
        """TABLE_INF が dict（要素1つ）の場合もリストに正規化."""
        resp_data = {
            "GET_STATS_LIST": {
                "RESULT": {"STATUS": 0},
                "DATALIST_INF": {
                    "TABLE_INF": {
                        "@id": "001",
                        "STAT_NAME": "テスト",
                        "GOV_ORG": "省庁",
                        "TITLE": "タイトル",
                    }
                },
            }
        }
        mock_resp = _mock_response(resp_data)
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with client:
                tables = await client.search_stats("テスト")
        assert len(tables) == 1


# ------------------------------------------------------------------
# get_meta_info
# ------------------------------------------------------------------


META_RESPONSE = {
    "GET_META_INFO": {
        "RESULT": {"STATUS": 0},
        "CLASS_INF": {
            "CLASS_OBJ": [
                {
                    "@id": "tab",
                    "@name": "表章項目",
                    "CLASS": [
                        {"@code": "001", "@name": "人口", "@level": "1"},
                        {"@code": "002", "@name": "世帯数", "@level": "1"},
                    ],
                },
                {
                    "@id": "area",
                    "@name": "地域",
                    "CLASS": {"@code": "13000", "@name": "東京都", "@level": "2"},
                },
            ]
        },
    }
}


class TestGetMetaInfo:
    @pytest.mark.asyncio
    async def test_parse_meta(self, client):
        mock_resp = _mock_response(META_RESPONSE)
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with client:
                meta = await client.get_meta_info("0003448237")

        assert meta.table_id == "0003448237"
        assert len(meta.class_objects) == 2

        tab = meta.get_class_object("tab")
        assert tab is not None
        assert len(tab.items) == 2
        assert tab.items[0].name == "人口"

        # area は CLASS が dict（1件）→ リスト化されるか
        area = meta.get_class_object("area")
        assert area is not None
        assert len(area.items) == 1
        assert area.items[0].name == "東京都"

    @pytest.mark.asyncio
    async def test_resolve_code(self, client):
        mock_resp = _mock_response(META_RESPONSE)
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with client:
                meta = await client.get_meta_info("0003448237")

        assert meta.resolve_code("area", "13000") == "東京都"
        assert meta.resolve_code("tab", "001") == "人口"
        assert meta.resolve_code("tab", "999") is None
        assert meta.resolve_code("unknown", "001") is None


# ------------------------------------------------------------------
# get_stats_data
# ------------------------------------------------------------------


STATS_DATA_RESPONSE = {
    "GET_STATS_DATA": {
        "RESULT": {"STATUS": 0},
        "STATISTICAL_DATA": {
            "RESULT_INF": {"TOTAL_NUMBER": 2},
            "CLASS_INF": {
                "CLASS_OBJ": [
                    {
                        "@id": "tab",
                        "@name": "表章項目",
                        "CLASS": [{"@code": "001", "@name": "人口"}],
                    },
                    {
                        "@id": "area",
                        "@name": "地域",
                        "CLASS": [{"@code": "13000", "@name": "東京都"}],
                    },
                    {
                        "@id": "time",
                        "@name": "時間軸",
                        "CLASS": [
                            {"@code": "2020000000", "@name": "2020年"},
                            {"@code": "2015000000", "@name": "2015年"},
                        ],
                    },
                ]
            },
            "DATA_INF": {
                "VALUE": [
                    {
                        "@tab": "001",
                        "@area": "13000",
                        "@time": "2020000000",
                        "$": "13960000",
                    },
                    {
                        "@tab": "001",
                        "@area": "13000",
                        "@time": "2015000000",
                        "$": "13515000",
                    },
                ]
            },
        },
    }
}


class TestGetStatsData:
    @pytest.mark.asyncio
    async def test_parse_stats_data(self, client):
        mock_resp = _mock_response(STATS_DATA_RESPONSE)
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with client:
                result = await client.get_stats_data(
                    "0003448237", cd_area="13000"
                )

        assert result.table_id == "0003448237"
        assert result.total_count == 2
        assert len(result.values) == 2

        v0 = result.values[0]
        assert v0.value == "13960000"
        assert v0.dimensions["tab"] == "001"
        assert v0.dimensions["area"] == "13000"
        assert v0.dimensions["time"] == "2020000000"

        # メタ情報でコード変換できるか
        assert result.meta_info.resolve_code("area", "13000") == "東京都"
        assert result.meta_info.resolve_code("time", "2020000000") == "2020年"


# ------------------------------------------------------------------
# APIエラー
# ------------------------------------------------------------------


class TestApiError:
    @pytest.mark.asyncio
    async def test_api_error_raised(self, client):
        error_resp = _mock_response(
            {
                "GET_STATS_LIST": {
                    "RESULT": {
                        "STATUS": 100,
                        "ERROR_MSG": "パラメータエラー",
                    }
                }
            }
        )
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=error_resp
        ):
            async with client:
                with pytest.raises(EStatApiError, match="パラメータエラー"):
                    await client.search_stats("test")
