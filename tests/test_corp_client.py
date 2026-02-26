"""法人番号 API クライアントのユニットテスト."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from japan_data_mcp.corp.client import CorpClient, _text
from japan_data_mcp.corp.models import Corporation, CorpApiError


def _make_response(status_code: int, text: str) -> httpx.Response:
    """テスト用のhttpx.Responseを作成する."""
    request = httpx.Request("GET", "https://test.example.com/")
    return httpx.Response(status_code, text=text, request=request)

# ------------------------------------------------------------------
# XML パースのテスト
# ------------------------------------------------------------------

SAMPLE_XML_RESPONSE = """\
<?xml version="1.0" encoding="UTF-8"?>
<corporations>
  <lastUpdateDate>2026-02-26</lastUpdateDate>
  <count>2</count>
  <divideNumber>1</divideNumber>
  <divideSize>10</divideSize>
  <corporation>
    <sequenceNumber>1</sequenceNumber>
    <corporateNumber>2180001011843</corporateNumber>
    <process>12</process>
    <correct>0</correct>
    <updateDate>2023-04-01</updateDate>
    <changeDate>2023-04-01</changeDate>
    <name>トヨタ自動車株式会社</name>
    <nameImageId/>
    <kind>301</kind>
    <prefectureName>愛知県</prefectureName>
    <cityName>豊田市</cityName>
    <streetNumber>トヨタ町１番地</streetNumber>
    <addressImageId/>
    <prefectureCode>23</prefectureCode>
    <cityCode>211</cityCode>
    <postCode>4711195</postCode>
    <addressOutside/>
    <addressOutsideImageId/>
    <closeDate/>
    <closeCause/>
    <successorCorporateNumber/>
    <changeCause/>
    <assignmentDate>2015-10-05</assignmentDate>
    <latest>1</latest>
    <enName/>
    <enPrefectureName/>
    <enCityName/>
    <enAddressOutside/>
    <furigana>トヨタジドウシャ</furigana>
    <hihyoji>0</hihyoji>
  </corporation>
  <corporation>
    <sequenceNumber>2</sequenceNumber>
    <corporateNumber>5180001067335</corporateNumber>
    <process>01</process>
    <correct>0</correct>
    <updateDate>2020-01-01</updateDate>
    <changeDate>2020-01-01</changeDate>
    <name>トヨタ産業株式会社</name>
    <nameImageId/>
    <kind>301</kind>
    <prefectureName>東京都</prefectureName>
    <cityName>千代田区</cityName>
    <streetNumber>丸の内１丁目</streetNumber>
    <addressImageId/>
    <prefectureCode>13</prefectureCode>
    <cityCode>101</cityCode>
    <postCode>1000005</postCode>
    <addressOutside/>
    <addressOutsideImageId/>
    <closeDate/>
    <closeCause/>
    <successorCorporateNumber/>
    <changeCause/>
    <assignmentDate>2020-01-01</assignmentDate>
    <latest>1</latest>
    <enName/>
    <enPrefectureName/>
    <enCityName/>
    <enAddressOutside/>
    <furigana>トヨタサンギョウ</furigana>
    <hihyoji>0</hihyoji>
  </corporation>
</corporations>
"""

SAMPLE_ERROR_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<corporations>
  <errors>
    <error>
      <message>パラメータが不正です</message>
    </error>
  </errors>
</corporations>
"""


class TestXmlParsing:
    def test_parse_corporations(self):
        """XMLレスポンスを正しくパースできる."""
        resp = _make_response(200, SAMPLE_XML_RESPONSE)
        client = CorpClient.__new__(CorpClient)
        corps = client._parse_response(resp, 10)

        assert len(corps) == 2
        assert corps[0].corporate_number == "2180001011843"
        assert corps[0].name == "トヨタ自動車株式会社"
        assert corps[0].kind == "301"
        assert corps[0].prefecture_name == "愛知県"
        assert corps[0].city_name == "豊田市"
        assert corps[0].furigana == "トヨタジドウシャ"
        assert corps[0].prefecture_code == "23"

    def test_parse_with_limit(self):
        """limitで件数を制限できる."""
        resp = _make_response(200, SAMPLE_XML_RESPONSE)
        client = CorpClient.__new__(CorpClient)
        corps = client._parse_response(resp, 1)

        assert len(corps) == 1

    def test_parse_error_response(self):
        """エラーレスポンスで CorpApiError が発生する."""
        resp = _make_response(200, SAMPLE_ERROR_XML)
        client = CorpClient.__new__(CorpClient)

        with pytest.raises(CorpApiError) as exc_info:
            client._parse_response(resp, 10)
        assert "パラメータが不正" in str(exc_info.value)

    def test_parse_404(self):
        """404レスポンスで CorpApiError が発生する."""
        resp = _make_response(404, "")
        client = CorpClient.__new__(CorpClient)

        with pytest.raises(CorpApiError) as exc_info:
            client._parse_response(resp, 10)
        assert exc_info.value.status_code == 404

    def test_parse_empty_response(self):
        """空のレスポンスで空リストが返る."""
        xml = '<?xml version="1.0" encoding="UTF-8"?><corporations></corporations>'
        resp = _make_response(200, xml)
        client = CorpClient.__new__(CorpClient)
        corps = client._parse_response(resp, 10)

        assert corps == []


# ------------------------------------------------------------------
# モデルのテスト
# ------------------------------------------------------------------


class TestCorporationModel:
    def test_kind_label(self):
        corp = Corporation(
            corporate_number="1234567890123",
            name="テスト株式会社",
            kind="301",
        )
        assert corp.kind_label == "株式会社"

    def test_kind_label_unknown(self):
        corp = Corporation(
            corporate_number="1234567890123",
            name="テスト",
            kind="999",
        )
        assert corp.kind_label == "999"

    def test_is_active(self):
        corp = Corporation(
            corporate_number="1234567890123",
            name="テスト",
        )
        assert corp.is_active is True

    def test_is_closed(self):
        corp = Corporation(
            corporate_number="1234567890123",
            name="テスト",
            close_date="2024-01-01",
        )
        assert corp.is_active is False

    def test_full_address(self):
        corp = Corporation(
            corporate_number="1234567890123",
            name="テスト",
            prefecture_name="東京都",
            city_name="千代田区",
            street_number="丸の内１丁目",
        )
        assert corp.full_address == "東京都千代田区丸の内１丁目"

    def test_verification_url(self):
        corp = Corporation(
            corporate_number="2180001011843",
            name="テスト",
        )
        assert "2180001011843" in corp.verification_url
        assert "houjin-bangou.nta.go.jp" in corp.verification_url


# ------------------------------------------------------------------
# _text ヘルパーのテスト
# ------------------------------------------------------------------


class TestTextHelper:
    def test_existing_element(self):
        import xml.etree.ElementTree as ET

        root = ET.fromstring("<root><name>テスト</name></root>")
        assert _text(root, "name") == "テスト"

    def test_missing_element(self):
        import xml.etree.ElementTree as ET

        root = ET.fromstring("<root></root>")
        assert _text(root, "name") == ""

    def test_empty_element(self):
        import xml.etree.ElementTree as ET

        root = ET.fromstring("<root><name/></root>")
        assert _text(root, "name") == ""


# ------------------------------------------------------------------
# クライアントの初期化テスト
# ------------------------------------------------------------------


class TestCorpClientInit:
    def test_raises_without_app_id(self, monkeypatch):
        monkeypatch.delenv("CORP_APP_ID", raising=False)
        with pytest.raises(ValueError, match="CORP_APP_ID"):
            CorpClient()

    def test_accepts_explicit_app_id(self):
        client = CorpClient(app_id="test-id")
        assert client._app_id == "test-id"
