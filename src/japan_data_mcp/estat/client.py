"""e-Stat API 非同期クライアント."""

from __future__ import annotations

import os
from typing import Any

import httpx

from japan_data_mcp.estat.models import (
    ClassItem,
    ClassObject,
    DataValue,
    EStatApiError,
    MetaInfo,
    StatsData,
    TableInfo,
)
from japan_data_mcp.utils.env import load_env_file

BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/"


class EStatClient:
    """e-Stat API 非同期クライアント.

    Usage::

        async with EStatClient() as client:
            tables = await client.search_stats("人口")
            meta = await client.get_meta_info(tables[0].id)
            data = await client.get_stats_data(tables[0].id, cd_area="13000")
    """

    def __init__(self, app_id: str | None = None) -> None:
        if app_id is None:
            load_env_file()
            app_id = os.environ.get("ESTAT_APP_ID", "")
        if not app_id:
            raise ValueError(
                "ESTAT_APP_ID が設定されていません。"
                "環境変数またはコンストラクタ引数で指定してください。"
            )
        self._app_id = app_id
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> EStatClient:
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "EStatClient は async with 文で使用してください。"
            )
        return self._client

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    async def _request(
        self, endpoint: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """APIリクエストを送信し、JSONレスポンスを返す."""
        params["appId"] = self._app_id
        resp = await self._http.get(f"{BASE_URL}{endpoint}", params=params)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        result = self._extract_result(data)
        if result:
            status = result.get("STATUS", 0)
            # STATUS 0=正常, 1=正常だが該当データなし, 2+=エラー
            # STATUS 1 はデータ空として正常扱い（呼び出し側で空リスト判定）
            if isinstance(status, int) and status >= 2:
                raise EStatApiError(
                    status=status,
                    message=result.get("ERROR_MSG", "不明なエラー"),
                )
        return data

    @staticmethod
    def _extract_result(data: dict[str, Any]) -> dict[str, Any] | None:
        """レスポンス最上位から RESULT オブジェクトを探す."""
        for value in data.values():
            if isinstance(value, dict) and "RESULT" in value:
                return value["RESULT"]  # type: ignore[no-any-return]
        return None

    @staticmethod
    def _ensure_list(obj: Any) -> list[Any]:
        """e-Stat APIは要素が1つの場合dictで返すことがあるのでlistに正規化."""
        if obj is None:
            return []
        if isinstance(obj, dict):
            return [obj]
        return obj  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # 統計表検索 (getStatsList)
    # ------------------------------------------------------------------

    async def search_stats(
        self,
        keyword: str,
        *,
        survey_years: str | None = None,
        stats_field: str | None = None,
        stats_code: str | None = None,
        limit: int = 20,
        start_position: int = 1,
    ) -> list[TableInfo]:
        """キーワードで統計表を検索する.

        Args:
            keyword: 検索キーワード（例: "人口", "国勢調査"）
            survey_years: 調査年（例: "2020", "2015-2020"）
            stats_field: 統計分野コード（例: "02" = 人口・世帯）
            stats_code: 政府統計コード
            limit: 取得件数上限
            start_position: 取得開始位置

        Returns:
            統計表情報のリスト
        """
        params: dict[str, Any] = {
            "searchWord": keyword,
            "limit": limit,
            "startPosition": start_position,
        }
        if survey_years:
            params["surveyYears"] = survey_years
        if stats_field:
            params["statsField"] = stats_field
        if stats_code:
            params["statsCode"] = stats_code

        data = await self._request("getStatsList", params)

        datalist = data.get("GET_STATS_LIST", {}).get("DATALIST_INF", {})
        tables_raw = self._ensure_list(datalist.get("TABLE_INF"))
        return [self._parse_table_info(t) for t in tables_raw]

    @staticmethod
    def _parse_table_info(raw: dict[str, Any]) -> TableInfo:
        stat_name = raw.get("STAT_NAME", "")
        gov_org = raw.get("GOV_ORG", "")
        title = raw.get("TITLE", "")

        # survey_date / open_date は int で返る場合がある（例: 0）
        survey_date = raw.get("SURVEY_DATE")
        open_date = raw.get("OPEN_DATE")

        return TableInfo(
            id=raw.get("@id", ""),
            stat_name=(
                stat_name.get("$", "")
                if isinstance(stat_name, dict)
                else str(stat_name)
            ),
            gov_org=(
                gov_org.get("$", "")
                if isinstance(gov_org, dict)
                else str(gov_org)
            ),
            title=(
                title.get("$", "") if isinstance(title, dict) else str(title)
            ),
            survey_date=str(survey_date) if survey_date is not None else None,
            open_date=str(open_date) if open_date is not None else None,
            small_area=raw.get("SMALL_AREA", 0) == 1,
        )

    # ------------------------------------------------------------------
    # メタ情報取得 (getMetaInfo)
    # ------------------------------------------------------------------

    async def get_meta_info(self, stats_data_id: str) -> MetaInfo:
        """統計表のメタ情報（分類コード体系）を取得する.

        Args:
            stats_data_id: 統計表ID（例: "0003448237"）

        Returns:
            分類オブジェクト一覧を含む MetaInfo
        """
        data = await self._request(
            "getMetaInfo", {"statsDataId": stats_data_id}
        )

        class_inf = (
            data.get("GET_META_INFO", {})
            .get("CLASS_INF", {})
            .get("CLASS_OBJ", [])
        )
        class_objects = [
            self._parse_class_object(co)
            for co in self._ensure_list(class_inf)
        ]
        return MetaInfo(table_id=stats_data_id, class_objects=class_objects)

    @staticmethod
    def _parse_class_object(raw: dict[str, Any]) -> ClassObject:
        classes = raw.get("CLASS", [])
        if isinstance(classes, dict):
            classes = [classes]

        items = [
            ClassItem(
                code=c.get("@code", ""),
                name=c.get("@name", ""),
                level=c.get("@level"),
                unit=c.get("@unit"),
                parent_code=c.get("@parentCode"),
            )
            for c in classes
        ]
        return ClassObject(
            id=raw.get("@id", ""),
            name=raw.get("@name", ""),
            items=items,
        )

    # ------------------------------------------------------------------
    # 統計データ取得 (getStatsData)
    # ------------------------------------------------------------------

    async def get_stats_data(
        self,
        stats_data_id: str,
        *,
        cd_area: str | None = None,
        cd_tab: str | None = None,
        cd_time: str | None = None,
        cd_cat01: str | None = None,
        limit: int | None = None,
        start_position: int | None = None,
    ) -> StatsData:
        """統計データを取得する（メタ情報付き）.

        Args:
            stats_data_id: 統計表ID
            cd_area: 地域コード（例: "13000" = 東京都）
            cd_tab: 表章項目コード
            cd_time: 時間軸コード
            cd_cat01: 分類事項01コード
            limit: 取得件数上限
            start_position: 取得開始位置

        Returns:
            メタ情報とデータ値を含む StatsData
        """
        params: dict[str, Any] = {
            "statsDataId": stats_data_id,
            "sectionHeaderFlg": 2,
        }
        if cd_area:
            params["cdArea"] = cd_area
        if cd_tab:
            params["cdTab"] = cd_tab
        if cd_time:
            params["cdTime"] = cd_time
        if cd_cat01:
            params["cdCat01"] = cd_cat01
        if limit is not None:
            params["limit"] = limit
        if start_position is not None:
            params["startPosition"] = start_position

        data = await self._request("getStatsData", params)
        stat_data = (
            data.get("GET_STATS_DATA", {}).get("STATISTICAL_DATA", {})
        )

        # メタ情報をパース
        class_inf = stat_data.get("CLASS_INF", {}).get("CLASS_OBJ", [])
        class_objects = [
            self._parse_class_object(co)
            for co in self._ensure_list(class_inf)
        ]
        meta = MetaInfo(table_id=stats_data_id, class_objects=class_objects)

        # データ値をパース
        data_inf = stat_data.get("DATA_INF", {})
        values_raw = self._ensure_list(data_inf.get("VALUE"))
        dim_keys = [co.id for co in class_objects]
        values = [self._parse_data_value(v, dim_keys) for v in values_raw]

        # 総件数
        result_inf = stat_data.get("RESULT_INF", {})
        total_number = result_inf.get("TOTAL_NUMBER")

        return StatsData(
            table_id=stats_data_id,
            meta_info=meta,
            values=values,
            total_count=(
                int(total_number) if total_number is not None else None
            ),
        )

    @staticmethod
    def _parse_data_value(
        raw: dict[str, Any], dim_keys: list[str]
    ) -> DataValue:
        dimensions: dict[str, str] = {}
        for key in dim_keys:
            at_key = f"@{key}"
            if at_key in raw:
                dimensions[key] = raw[at_key]
        return DataValue(value=raw.get("$"), dimensions=dimensions)
