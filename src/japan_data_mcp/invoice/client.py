"""適格請求書発行事業者公表 Web-API クライアント.

国税庁のインボイス公表システム Web-API (Ver.1) を使用して、
登録番号検索・日付指定有効性確認を行う非同期クライアント。

レスポンスは JSON 形式（type=21）。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from japan_data_mcp.invoice.models import InvoiceApiError, InvoiceIssuer
from japan_data_mcp.utils.env import load_env_file

BASE_URL = "https://web-api.invoice-kohyo.nta.go.jp/1"


class InvoiceClient:
    """適格請求書発行事業者公表 Web-API 非同期クライアント.

    Usage::

        async with InvoiceClient() as client:
            issuers = await client.get_by_number(["T1180301018771"])
            issuer = await client.validate_on_date("T1180301018771", "2024-12-01")
    """

    def __init__(self, app_id: str | None = None) -> None:
        if app_id is None:
            load_env_file()
            app_id = os.environ.get("CORP_APP_ID", "")
        if not app_id:
            raise ValueError(
                "CORP_APP_ID が設定されていません。"
                "環境変数またはコンストラクタ引数で指定してください。\n"
                "取得方法: https://www.houjin-bangou.nta.go.jp/webapi/"
            )
        self._app_id = app_id
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> InvoiceClient:
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
                "InvoiceClient は async with 文で使用してください。"
            )
        return self._client

    # ------------------------------------------------------------------
    # 登録番号検索
    # ------------------------------------------------------------------

    async def get_by_number(
        self,
        numbers: list[str],
        *,
        history: bool = False,
    ) -> list[InvoiceIssuer]:
        """登録番号から事業者情報を取得する.

        Args:
            numbers: 登録番号のリスト（T+13桁、最大10件）
            history: 履歴情報を含めるか

        Returns:
            事業者情報のリスト
        """
        if not numbers:
            return []
        if len(numbers) > 10:
            numbers = numbers[:10]

        params: dict[str, Any] = {
            "id": self._app_id,
            "number": ",".join(numbers),
            "type": 21,
            "history": "1" if history else "0",
        }

        resp = await self._http.get(f"{BASE_URL}/num", params=params)
        return self._parse_response(resp)

    # ------------------------------------------------------------------
    # 日付指定有効性確認
    # ------------------------------------------------------------------

    async def validate_on_date(
        self,
        number: str,
        day: str,
    ) -> InvoiceIssuer | None:
        """指定日時点での登録状態を確認する.

        Args:
            number: 登録番号（T+13桁）
            day: 基準日（YYYY-MM-DD）

        Returns:
            事業者情報（該当なしの場合は None）
        """
        params: dict[str, Any] = {
            "id": self._app_id,
            "number": number,
            "day": day,
            "type": 21,
        }

        resp = await self._http.get(f"{BASE_URL}/valid", params=params)
        results = self._parse_response(resp)
        return results[0] if results else None

    # ------------------------------------------------------------------
    # JSON パース
    # ------------------------------------------------------------------

    def _parse_response(self, resp: httpx.Response) -> list[InvoiceIssuer]:
        """JSON レスポンスをパースして InvoiceIssuer リストに変換."""
        if resp.status_code == 404:
            raise InvoiceApiError(404, "アプリケーション ID が無効です。")
        if resp.status_code == 403:
            raise InvoiceApiError(403, "リクエスト制限に達しました。")
        if resp.status_code == 400:
            raise InvoiceApiError(400, "リクエストパラメータが不正です。")
        resp.raise_for_status()

        data = resp.json()

        announcement = data.get("announcement")
        if not announcement:
            return []

        return [InvoiceIssuer.model_validate(item) for item in announcement]
