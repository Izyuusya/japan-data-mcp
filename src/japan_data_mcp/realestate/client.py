"""国土交通省 不動産情報ライブラリ API クライアント.

不動産取引価格情報（XIT001）と都道府県内市区町村一覧（XIT002）を
取得する非同期クライアント。
"""

from __future__ import annotations

import asyncio
import gzip
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from japan_data_mcp.realestate.geotiles import (
    DEFAULT_RADII,
    deg2tile,
    geocode_point,
    tile_window,
)
from japan_data_mcp.realestate.models import (
    LandPrice,
    Municipality,
    RealEstateApiError,
    Transaction,
)
from japan_data_mcp.utils.env import load_env_file

_JST = timezone(timedelta(hours=9))


def current_year_jst() -> int:
    """現在の年（JST）を返す."""
    return datetime.now(_JST).year


BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"


def _extract_api_message(resp: httpx.Response) -> str:
    """上流の 400 応答から人間可読なメッセージを取り出す.

    上流は ``{"message": {"year": "'year'が指定されていません。"}}`` のように
    ネストした dict を返すことがある。
    """
    try:
        payload = resp.json()
    except Exception:
        return f"リクエストが不正です（HTTP {resp.status_code}）"
    message = payload.get("message", payload) if isinstance(payload, dict) else payload
    if isinstance(message, dict):
        parts = [str(v) for v in message.values()]
        message = " / ".join(parts)
    return str(message) or f"リクエストが不正です（HTTP {resp.status_code}）"

# 地価公示・地価調査ポイントAPI（XPT002）が対応するズームレベル。
DEFAULT_LAND_PRICE_ZOOM = 13
_MIN_LAND_PRICE_ZOOM = 13
_MAX_LAND_PRICE_ZOOM = 15

# 地価情報区分コード
PRICE_CLASSIFICATION_GOVERNMENT = "0"  # 国土交通省地価公示のみ
PRICE_CLASSIFICATION_PREFECTURE = "1"  # 都道府県地価調査のみ

# 用途区分コード
USE_CATEGORY_CODES: dict[str, str] = {
    "住宅地": "00",
    "宅地見込地": "03",
    "商業地": "05",
    "準工業地": "07",
    "工業地": "09",
    "市街化調整区域内現況宅地": "10",
    "市街地調整区域内現況林地": "13",
    "林地": "20",
}


class RealEstateClient:
    """不動産情報ライブラリ API 非同期クライアント.

    Usage::

        async with RealEstateClient() as client:
            txns = await client.get_transactions("13", city_code="13101", year=2023)
            cities = await client.get_municipalities("13")
    """

    def __init__(self, api_key: str | None = None) -> None:
        if api_key is None:
            load_env_file()
            api_key = os.environ.get("REALESTATE_API_KEY", "")
        if not api_key:
            raise ValueError(
                "REALESTATE_API_KEY が設定されていません。"
                "環境変数またはコンストラクタ引数で指定してください。\n"
                "取得方法: https://www.reinfolib.mlit.go.jp/ex-api/"
            )
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> RealEstateClient:
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Ocp-Apim-Subscription-Key": self._api_key,
            },
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "RealEstateClient は async with 文で使用してください。"
            )
        return self._client

    # ------------------------------------------------------------------
    # 不動産取引価格情報 (XIT001)
    # ------------------------------------------------------------------

    async def get_transactions(
        self,
        prefecture_code: str,
        *,
        city_code: str | None = None,
        year: int | None = None,
        quarter: int | None = None,
    ) -> list[Transaction]:
        """不動産取引価格情報を取得する.

        Args:
            prefecture_code: 都道府県コード（2桁、例: "13"）
            city_code: 市区町村コード（5桁、省略可）
            year: 取引年（例: 2023）。**上流APIは year 必須**のため、
                省略時は当年（JST）を補完する（``'year'が指定されていません`` の400回避）。
            quarter: 四半期（1〜4、省略可）

        Returns:
            取引データのリスト
        """
        params: dict[str, Any] = {
            "area": prefecture_code,
        }
        if city_code:
            params["city"] = city_code
        # 上流の XIT001 は year が必須（未指定だと HTTP 400）。当年で補完する。
        params["year"] = year if year is not None else current_year_jst()
        if quarter is not None:
            params["quarter"] = quarter

        data = await self._request("XIT001", params)
        raw_list = data.get("data", [])
        return [Transaction.model_validate(item) for item in raw_list]

    # ------------------------------------------------------------------
    # 都道府県内市区町村一覧 (XIT002)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 地価公示・地価調査ポイント (XPT002)
    # ------------------------------------------------------------------

    async def get_land_prices(
        self,
        prefecture_code: str,
        *,
        city_code: str | None = None,
        year: int,
        area_query: str = "",
        zoom: int = DEFAULT_LAND_PRICE_ZOOM,
        price_classification: str | None = None,
        use_category: str | None = None,
        radii: tuple[int, ...] = DEFAULT_RADII,
        max_tiles: int = 1200,
        concurrency: int = 5,
    ) -> tuple[list[LandPrice], bool]:
        """地価公示・地価調査の地点データを取得する.

        XPT002 は ``area``/``city`` を受け付けないため、代表点を中心にタイル窓を
        **段階的に広げて飽和を検出**し、``city_code`` でクライアント側フィルタする。

        Args:
            prefecture_code: 都道府県コード（2桁、例 "12"）
            city_code: 市区町村コード（5桁、例 "12212"）。省略時は都道府県全域
            year: 対象年（例 2026）
            area_query: 代表点検索に使う住所・地域名（例 "千葉県佐倉市"）
            zoom: XYZ タイルのズームレベル（13〜15）
            price_classification: "0"=地価公示のみ, "1"=地価調査のみ, None=両方
            use_category: 用途区分コード（"00" 住宅地, "05" 商業地 など）
            radii: 段階的に試す窓の半径（タイル数）
            max_tiles: 1回の窓で許容するタイル数の上限
            concurrency: 同時リクエスト数

        Returns:
            (地点リスト, 全域を覆えたか) のタプル。2つ目が False の場合は
            半径上限に達しても新規地点が増え続けており、市域の一部が欠落している。
        """
        if not _MIN_LAND_PRICE_ZOOM <= zoom <= _MAX_LAND_PRICE_ZOOM:
            raise ValueError(
                f"zoom は {_MIN_LAND_PRICE_ZOOM}〜{_MAX_LAND_PRICE_ZOOM} を指定してください"
                f"（指定値: {zoom}）"
            )

        center = await geocode_point(self._http, area_query)
        if center is None:
            raise RealEstateApiError(
                404,
                "地域の代表点を特定できませんでした。"
                "市区町村名（例「佐倉市」）または5桁の市区町村コードを指定してください。",
            )
        center_x, center_y = deg2tile(center[0], center[1], zoom)

        semaphore = asyncio.Semaphore(max(1, concurrency))
        seen: set[Any] = set()
        land_prices: list[LandPrice] = []
        saturated = False
        previous_total = 0

        for radius in radii:
            tiles = tile_window(center_x, center_y, radius, max_tiles=max_tiles)

            async def _fetch(x: int, y: int) -> dict[str, Any]:
                async with semaphore:
                    return await self._request(
                        "XPT002",
                        {
                            "response_format": "geojson",
                            "z": zoom,
                            "x": x,
                            "y": y,
                            "year": year,
                            "priceClassification": price_classification,
                            "useCategoryCode": use_category,
                        },
                    )

            payloads = await asyncio.gather(*(_fetch(x, y) for x, y in tiles))

            for payload in payloads:
                for feature in payload.get("features", []):
                    props = feature.get("properties") or {}
                    if city_code and props.get("city_code") != city_code:
                        continue
                    key = props.get("point_id") or (
                        props.get("standard_lot_number_ja"),
                        props.get("location_number_ja"),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    land_prices.append(LandPrice.model_validate(props))

            if len(land_prices) == previous_total:
                # 窓を広げても新規地点が増えない = 全域を覆えた
                saturated = True
                break
            previous_total = len(land_prices)

        return land_prices, saturated

    async def get_municipalities(
        self,
        prefecture_code: str,
    ) -> list[Municipality]:
        """都道府県内の市区町村一覧を取得する.

        Args:
            prefecture_code: 都道府県コード（2桁、例: "13"）

        Returns:
            市区町村のリスト
        """
        data = await self._request(
            "XIT002", {"area": prefecture_code}
        )
        raw_list = data.get("data", [])
        return [Municipality.model_validate(item) for item in raw_list]

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    async def _request(
        self, endpoint: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """APIリクエストを送信し、JSONレスポンスを返す.

        レスポンスが gzip 圧縮の場合は自動展開する。
        """
        resp = await self._http.get(f"{BASE_URL}/{endpoint}", params=params)

        if resp.status_code == 404:
            # XIT001 はデータなしの場合 404 を返す
            return {"data": [], "features": []}
        if resp.status_code == 400:
            # 上流はパラメータ不備を 400 + {"message": "..."} で返す
            raise RealEstateApiError(400, _extract_api_message(resp))
        if resp.status_code == 401:
            raise RealEstateApiError(401, "API キーが無効です。")
        if resp.status_code == 429:
            raise RealEstateApiError(429, "リクエスト制限に達しました。")
        resp.raise_for_status()

        # gzip 圧縮チェック（実際のバイト列で判定）
        # httpx が自動展開済みの場合は content-encoding ヘッダーだけでは
        # 判定できないため、マジックバイトを確認する
        if resp.content[:2] == b"\x1f\x8b":
            text = gzip.decompress(resp.content).decode("utf-8")
            import json

            return json.loads(text)  # type: ignore[no-any-return]

        return resp.json()  # type: ignore[no-any-return]
