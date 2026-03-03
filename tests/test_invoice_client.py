"""適格請求書発行事業者公表 API クライアントのユニットテスト."""

import json

import httpx
import pytest

from japan_data_mcp.invoice.client import InvoiceClient
from japan_data_mcp.invoice.models import InvoiceApiError, InvoiceIssuer


def _make_response(status_code: int, data: dict | str) -> httpx.Response:
    """テスト用のhttpx.Responseを作成する."""
    request = httpx.Request("GET", "https://test.example.com/")
    if isinstance(data, dict):
        text = json.dumps(data, ensure_ascii=False)
    else:
        text = data
    return httpx.Response(status_code, text=text, request=request)


# ------------------------------------------------------------------
# サンプルデータ
# ------------------------------------------------------------------

SAMPLE_ANNOUNCEMENT = {
    "sequenceNumber": "1",
    "registratedNumber": "T2180001011843",
    "process": "01",
    "correct": "0",
    "kind": "2",
    "country": "1",
    "latest": "1",
    "registrationDate": "2023-10-01",
    "updateDate": "2023-09-15",
    "disposalDate": "",
    "expireDate": "",
    "address": "愛知県豊田市トヨタ町１番地",
    "addressPrefectureCode": "23",
    "addressCityCode": "211",
    "addressRequest": "",
    "addressRequestPrefectureCode": "",
    "addressRequestCityCode": "",
    "kana": "",
    "name": "トヨタ自動車株式会社",
    "addressInside": "",
    "addressInsidePrefectureCode": "",
    "addressInsideCityCode": "",
    "tradeName": "",
    "popularName_previousName": "",
}

SAMPLE_CANCELLED = {
    "sequenceNumber": "1",
    "registratedNumber": "T9999999999999",
    "process": "03",
    "correct": "0",
    "kind": "2",
    "country": "1",
    "latest": "1",
    "registrationDate": "2023-10-01",
    "updateDate": "2024-06-01",
    "disposalDate": "2024-06-01",
    "expireDate": "",
    "address": "東京都千代田区丸の内",
    "addressPrefectureCode": "13",
    "addressCityCode": "101",
    "addressRequest": "",
    "addressRequestPrefectureCode": "",
    "addressRequestCityCode": "",
    "kana": "",
    "name": "取消テスト株式会社",
    "addressInside": "",
    "addressInsidePrefectureCode": "",
    "addressInsideCityCode": "",
    "tradeName": "",
    "popularName_previousName": "",
}

SAMPLE_JSON_RESPONSE = {
    "lastUpdateDate": "2026-03-01",
    "count": "1",
    "divideNumber": "1",
    "divideSize": "1",
    "announcement": [SAMPLE_ANNOUNCEMENT],
}

SAMPLE_MULTI_RESPONSE = {
    "lastUpdateDate": "2026-03-01",
    "count": "2",
    "divideNumber": "1",
    "divideSize": "1",
    "announcement": [SAMPLE_ANNOUNCEMENT, SAMPLE_CANCELLED],
}

SAMPLE_EMPTY_RESPONSE = {
    "lastUpdateDate": "2026-03-01",
    "count": "0",
    "divideNumber": "1",
    "divideSize": "1",
    "announcement": [],
}


# ------------------------------------------------------------------
# JSON パースのテスト
# ------------------------------------------------------------------


class TestJsonParsing:
    def test_parse_single(self):
        """JSONレスポンスを正しくパースできる."""
        resp = _make_response(200, SAMPLE_JSON_RESPONSE)
        client = InvoiceClient.__new__(InvoiceClient)
        issuers = client._parse_response(resp)

        assert len(issuers) == 1
        assert issuers[0].registrated_number == "T2180001011843"
        assert issuers[0].name == "トヨタ自動車株式会社"
        assert issuers[0].kind == "2"
        assert issuers[0].address == "愛知県豊田市トヨタ町１番地"
        assert issuers[0].registration_date == "2023-10-01"

    def test_parse_multiple(self):
        """複数件のレスポンスをパースできる."""
        resp = _make_response(200, SAMPLE_MULTI_RESPONSE)
        client = InvoiceClient.__new__(InvoiceClient)
        issuers = client._parse_response(resp)

        assert len(issuers) == 2
        assert issuers[0].name == "トヨタ自動車株式会社"
        assert issuers[1].name == "取消テスト株式会社"

    def test_parse_empty(self):
        """空のレスポンスで空リストが返る."""
        resp = _make_response(200, SAMPLE_EMPTY_RESPONSE)
        client = InvoiceClient.__new__(InvoiceClient)
        issuers = client._parse_response(resp)

        assert issuers == []

    def test_parse_no_announcement_key(self):
        """announcementキーがない場合に空リストが返る."""
        resp = _make_response(200, {"lastUpdateDate": "2026-03-01"})
        client = InvoiceClient.__new__(InvoiceClient)
        issuers = client._parse_response(resp)

        assert issuers == []

    def test_parse_404(self):
        """404レスポンスで InvoiceApiError が発生する."""
        resp = _make_response(404, "")
        client = InvoiceClient.__new__(InvoiceClient)

        with pytest.raises(InvoiceApiError) as exc_info:
            client._parse_response(resp)
        assert exc_info.value.status_code == 404

    def test_parse_403(self):
        """403レスポンスで InvoiceApiError が発生する."""
        resp = _make_response(403, "")
        client = InvoiceClient.__new__(InvoiceClient)

        with pytest.raises(InvoiceApiError) as exc_info:
            client._parse_response(resp)
        assert exc_info.value.status_code == 403

    def test_parse_400(self):
        """400レスポンスで InvoiceApiError が発生する."""
        resp = _make_response(400, "")
        client = InvoiceClient.__new__(InvoiceClient)

        with pytest.raises(InvoiceApiError) as exc_info:
            client._parse_response(resp)
        assert exc_info.value.status_code == 400


# ------------------------------------------------------------------
# モデルのテスト
# ------------------------------------------------------------------


class TestInvoiceIssuerModel:
    def test_from_api_data(self):
        """APIレスポンスからモデルを正しく構築できる."""
        issuer = InvoiceIssuer.model_validate(SAMPLE_ANNOUNCEMENT)
        assert issuer.registrated_number == "T2180001011843"
        assert issuer.name == "トヨタ自動車株式会社"
        assert issuer.process == "01"
        assert issuer.kind == "2"
        assert issuer.registration_date == "2023-10-01"

    def test_kind_label_corporate(self):
        issuer = InvoiceIssuer(registrated_number="T1234567890123", name="テスト", kind="2")
        assert issuer.kind_label == "法人"

    def test_kind_label_individual(self):
        issuer = InvoiceIssuer(registrated_number="T1234567890123", name="テスト", kind="1")
        assert issuer.kind_label == "個人"

    def test_kind_label_unknown(self):
        issuer = InvoiceIssuer(registrated_number="T1234567890123", name="テスト", kind="9")
        assert issuer.kind_label == "9"

    def test_process_label(self):
        issuer = InvoiceIssuer(registrated_number="T1234567890123", name="テスト", process="01")
        assert issuer.process_label == "新規登録"

    def test_process_label_cancel(self):
        issuer = InvoiceIssuer(registrated_number="T1234567890123", name="テスト", process="03")
        assert issuer.process_label == "登録取消"

    def test_is_registered_active(self):
        issuer = InvoiceIssuer(registrated_number="T1234567890123", name="テスト")
        assert issuer.is_registered is True

    def test_is_registered_cancelled(self):
        issuer = InvoiceIssuer(
            registrated_number="T1234567890123",
            name="テスト",
            disposal_date="2024-06-01",
        )
        assert issuer.is_registered is False

    def test_is_registered_expired(self):
        issuer = InvoiceIssuer(
            registrated_number="T1234567890123",
            name="テスト",
            expire_date="2024-12-31",
        )
        assert issuer.is_registered is False

    def test_status_label_active(self):
        issuer = InvoiceIssuer(registrated_number="T1234567890123", name="テスト")
        assert issuer.status_label == "登録中"

    def test_status_label_cancelled(self):
        issuer = InvoiceIssuer(
            registrated_number="T1234567890123",
            name="テスト",
            disposal_date="2024-06-01",
        )
        assert "取消" in issuer.status_label
        assert "2024-06-01" in issuer.status_label

    def test_status_label_expired(self):
        issuer = InvoiceIssuer(
            registrated_number="T1234567890123",
            name="テスト",
            expire_date="2024-12-31",
        )
        assert "失効" in issuer.status_label

    def test_display_address_corporate(self):
        issuer = InvoiceIssuer(
            registrated_number="T1234567890123",
            name="テスト",
            address="愛知県豊田市トヨタ町１番地",
        )
        assert issuer.display_address == "愛知県豊田市トヨタ町１番地"

    def test_display_address_request(self):
        issuer = InvoiceIssuer(
            registrated_number="T1234567890123",
            name="テスト",
            address_request="東京都渋谷区",
        )
        assert issuer.display_address == "東京都渋谷区"

    def test_display_address_empty(self):
        issuer = InvoiceIssuer(registrated_number="T1234567890123", name="テスト")
        assert issuer.display_address == ""

    def test_corp_number(self):
        issuer = InvoiceIssuer(registrated_number="T2180001011843", name="テスト")
        assert issuer.corp_number == "2180001011843"

    def test_corp_number_no_t(self):
        issuer = InvoiceIssuer(registrated_number="2180001011843", name="テスト")
        assert issuer.corp_number == "2180001011843"

    def test_verification_url(self):
        issuer = InvoiceIssuer(registrated_number="T2180001011843", name="テスト")
        assert "2180001011843" in issuer.verification_url
        assert "invoice-kohyo.nta.go.jp" in issuer.verification_url


# ------------------------------------------------------------------
# クライアント初期化のテスト
# ------------------------------------------------------------------


class TestInvoiceClientInit:
    def test_raises_without_app_id(self, monkeypatch):
        monkeypatch.delenv("CORP_APP_ID", raising=False)
        monkeypatch.setattr(
            "japan_data_mcp.invoice.client.load_env_file", lambda: None
        )
        with pytest.raises(ValueError, match="CORP_APP_ID"):
            InvoiceClient()

    def test_accepts_explicit_app_id(self):
        client = InvoiceClient(app_id="test-id")
        assert client._app_id == "test-id"


# ------------------------------------------------------------------
# InvoiceApiError のテスト
# ------------------------------------------------------------------


class TestInvoiceApiError:
    def test_error_message(self):
        error = InvoiceApiError(400, "パラメータ不正")
        assert error.status_code == 400
        assert error.message == "パラメータ不正"
        assert "400" in str(error)
        assert "パラメータ不正" in str(error)
