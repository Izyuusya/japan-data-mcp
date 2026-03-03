"""国税庁 法人番号 Web-API クライアント.

法人番号公表サイトの Web-API (Ver.4) を使用して、
法人名検索・法人番号検索を行う非同期クライアント。

レスポンスは XML 形式のみ（JSON 非対応）。
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from japan_data_mcp.corp.models import Corporation, CorpApiError
from japan_data_mcp.utils.env import load_env_file

BASE_URL = "https://api.houjin-bangou.nta.go.jp/4"


class CorpClient:
    """法人番号 Web-API 非同期クライアント.

    Usage::

        async with CorpClient() as client:
            results = await client.search_by_name("トヨタ")
            corp = await client.get_by_number(["2180001011843"])
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

    async def __aenter__(self) -> CorpClient:
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
                "CorpClient は async with 文で使用してください。"
            )
        return self._client

    # ------------------------------------------------------------------
    # 法人名検索
    # ------------------------------------------------------------------

    async def search_by_name(
        self,
        name: str,
        *,
        mode: int = 2,
        target: int = 1,
        prefecture_code: str | None = None,
        city_code: str | None = None,
        kind: str | None = None,
        close: int = 0,
        limit: int = 10,
    ) -> list[Corporation]:
        """法人名でキーワード検索する.

        Args:
            name: 検索キーワード（法人名）
            mode: 検索方式（1=前方一致, 2=部分一致）
            target: 検索対象（1=あいまい検索, 2=完全一致, 3=英語表記）
            prefecture_code: 都道府県コード（2桁、省略可）
            city_code: 市区町村コード（3桁、省略可）
            kind: 法人種別（"01"=国の機関〜"04"=その他、カンマ区切り可）
            close: 閉鎖法人を含めるか（0=含めない, 1=含める）
            limit: 最大取得件数（API最大 2000）

        Returns:
            法人情報のリスト
        """
        params: dict[str, Any] = {
            "id": self._app_id,
            "name": name,
            "type": 12,  # XML
            "mode": mode,
            "target": target,
            "history": 0,
            "close": close,
            "divide": 1,
        }
        if prefecture_code:
            params["prefecture"] = prefecture_code
        if city_code:
            params["city"] = city_code
        if kind:
            params["kind"] = kind

        resp = await self._http.get(f"{BASE_URL}/name", params=params)
        return self._parse_response(resp, limit)

    # ------------------------------------------------------------------
    # 法人番号取得
    # ------------------------------------------------------------------

    async def get_by_number(
        self,
        corp_numbers: list[str],
    ) -> list[Corporation]:
        """法人番号から法人情報を取得する.

        Args:
            corp_numbers: 法人番号のリスト（13桁、最大10件）

        Returns:
            法人情報のリスト
        """
        if not corp_numbers:
            return []
        if len(corp_numbers) > 10:
            corp_numbers = corp_numbers[:10]

        params: dict[str, Any] = {
            "id": self._app_id,
            "number": ",".join(corp_numbers),
            "type": 12,  # XML
            "history": 0,
        }

        resp = await self._http.get(f"{BASE_URL}/num", params=params)
        return self._parse_response(resp, len(corp_numbers))

    # ------------------------------------------------------------------
    # XML パース
    # ------------------------------------------------------------------

    def _parse_response(
        self, resp: httpx.Response, limit: int
    ) -> list[Corporation]:
        """XML レスポンスをパースして Corporation リストに変換."""
        if resp.status_code == 404:
            raise CorpApiError(404, "アプリケーション ID が無効です。")
        if resp.status_code == 403:
            raise CorpApiError(403, "リクエスト制限に達しました。")
        resp.raise_for_status()

        root = ET.fromstring(resp.text)

        # エラーチェック
        errors = root.find(".//errors")
        if errors is not None:
            error_el = errors.find("error")
            if error_el is not None:
                msg = _text(error_el, "message")
                raise CorpApiError(400, msg or "不明なエラー")

        # 法人データをパース
        results: list[Corporation] = []
        for corp_el in root.iter("corporation"):
            corp = Corporation(
                corporate_number=_text(corp_el, "corporateNumber"),
                name=_text(corp_el, "name"),
                kind=_text(corp_el, "kind"),
                prefecture_name=_text(corp_el, "prefectureName"),
                city_name=_text(corp_el, "cityName"),
                street_number=_text(corp_el, "streetNumber"),
                post_code=_text(corp_el, "postCode"),
                prefecture_code=_text(corp_el, "prefectureCode"),
                city_code=_text(corp_el, "cityCode"),
                assignment_date=_text(corp_el, "assignmentDate"),
                update_date=_text(corp_el, "updateDate"),
                change_date=_text(corp_el, "changeDate"),
                close_date=_text(corp_el, "closeDate"),
                close_cause=_text(corp_el, "closeCause"),
                furigana=_text(corp_el, "furigana"),
                process=_text(corp_el, "process"),
            )
            results.append(corp)
            if len(results) >= limit:
                break

        return results


def _text(parent: ET.Element, tag: str) -> str:
    """子要素のテキストを取得。存在しない場合は空文字列."""
    el = parent.find(tag)
    return el.text.strip() if el is not None and el.text else ""
