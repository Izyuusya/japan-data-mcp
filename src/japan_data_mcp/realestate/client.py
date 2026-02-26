"""国土交通省 不動産情報ライブラリ API クライアント.

不動産取引価格情報（XIT001）と都道府県内市区町村一覧（XIT002）を
取得する非同期クライアント。
"""

from __future__ import annotations

import gzip
import os
from typing import Any

import httpx

from japan_data_mcp.realestate.models import (
    Municipality,
    RealEstateApiError,
    Transaction,
)
from japan_data_mcp.utils.env import load_env_file

BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"


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
            year: 取引年（例: 2023）
            quarter: 四半期（1〜4、省略可）

        Returns:
            取引データのリスト
        """
        params: dict[str, Any] = {
            "area": prefecture_code,
        }
        if city_code:
            params["city"] = city_code
        if year is not None:
            params["year"] = year
        if quarter is not None:
            params["quarter"] = quarter

        data = await self._request("XIT001", params)
        raw_list = data.get("data", [])
        return [Transaction.model_validate(item) for item in raw_list]

    # ------------------------------------------------------------------
    # 都道府県内市区町村一覧 (XIT002)
    # ------------------------------------------------------------------

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
            return {"data": []}
        if resp.status_code == 401:
            raise RealEstateApiError(401, "API キーが無効です。")
        if resp.status_code == 429:
            raise RealEstateApiError(429, "リクエスト制限に達しました。")
        resp.raise_for_status()

        # gzip 圧縮チェック
        content_encoding = resp.headers.get("content-encoding", "")
        if content_encoding == "gzip" or resp.content[:2] == b"\x1f\x8b":
            text = gzip.decompress(resp.content).decode("utf-8")
            import json

            return json.loads(text)  # type: ignore[no-any-return]

        return resp.json()  # type: ignore[no-any-return]
