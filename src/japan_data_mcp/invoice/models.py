"""適格請求書発行事業者公表 API データモデル."""

from __future__ import annotations

from pydantic import BaseModel, Field


class InvoiceIssuer(BaseModel):
    """適格請求書発行事業者."""

    sequence_number: str = Field(default="", alias="sequenceNumber")
    """一連番号."""

    registrated_number: str = Field(default="", alias="registratedNumber")
    """登録番号（T + 13桁）."""

    process: str = Field(default="", alias="process")
    """事業者処理区分（01=新規登録, 02=公表内容変更, 03=取消, 04=失効, 99=削除）."""

    correct: str = Field(default="", alias="correct")
    """訂正区分（0=訂正なし, 1=訂正あり）."""

    kind: str = Field(default="", alias="kind")
    """人格区分（1=個人, 2=法人）."""

    country: str = Field(default="", alias="country")
    """国内外区分（1=国内, 2=国外（法人）, 3=国外（個人））."""

    latest: str = Field(default="", alias="latest")
    """最新履歴（0=過去, 1=最新）."""

    registration_date: str = Field(default="", alias="registrationDate")
    """登録年月日."""

    update_date: str = Field(default="", alias="updateDate")
    """更新年月日."""

    disposal_date: str = Field(default="", alias="disposalDate")
    """取消年月日."""

    expire_date: str = Field(default="", alias="expireDate")
    """失効年月日."""

    address: str = Field(default="", alias="address")
    """本店又は主たる事務所の所在地（法人）."""

    address_prefecture_code: str = Field(
        default="", alias="addressPrefectureCode"
    )
    """所在地 都道府県コード（法人）."""

    address_city_code: str = Field(default="", alias="addressCityCode")
    """所在地 市区町村コード（法人）."""

    address_request: str = Field(default="", alias="addressRequest")
    """所在地（公表申出）."""

    address_request_prefecture_code: str = Field(
        default="", alias="addressRequestPrefectureCode"
    )
    """所在地 都道府県コード（公表申出）."""

    address_request_city_code: str = Field(
        default="", alias="addressRequestCityCode"
    )
    """所在地 市区町村コード（公表申出）."""

    kana: str = Field(default="", alias="kana")
    """フリガナ."""

    name: str = Field(default="", alias="name")
    """氏名又は名称."""

    address_inside: str = Field(default="", alias="addressInside")
    """国内における主たる事務所の所在地."""

    address_inside_prefecture_code: str = Field(
        default="", alias="addressInsidePrefectureCode"
    )
    """国内事務所 都道府県コード."""

    address_inside_city_code: str = Field(
        default="", alias="addressInsideCityCode"
    )
    """国内事務所 市区町村コード."""

    trade_name: str = Field(default="", alias="tradeName")
    """主たる屋号（個人事業主）."""

    popular_name_previous_name: str = Field(
        default="", alias="popularName_previousName"
    )
    """通称・旧姓."""

    model_config = {"populate_by_name": True}

    @property
    def kind_label(self) -> str:
        """人格区分の日本語ラベル."""
        return _KIND_LABELS.get(self.kind, self.kind)

    @property
    def process_label(self) -> str:
        """処理区分の日本語ラベル."""
        return _PROCESS_LABELS.get(self.process, self.process)

    @property
    def is_registered(self) -> bool:
        """現在登録有効かどうか（取消・失効がなければ有効）."""
        return not self.disposal_date and not self.expire_date

    @property
    def status_label(self) -> str:
        """登録状態ラベル."""
        if self.disposal_date:
            return f"取消（{self.disposal_date}）"
        if self.expire_date:
            return f"失効（{self.expire_date}）"
        return "登録中"

    @property
    def display_address(self) -> str:
        """表示用所在地（法人住所 > 公表申出住所 > 国内事務所住所）."""
        return self.address or self.address_request or self.address_inside

    @property
    def corp_number(self) -> str:
        """法人番号（T を除いた13桁）."""
        num = self.registrated_number
        if num.startswith("T"):
            return num[1:]
        return num

    @property
    def verification_url(self) -> str:
        """インボイス公表サイトの検証用URL."""
        return (
            "https://www.invoice-kohyo.nta.go.jp/"
            f"henkorireki-johoto.html?selHouzinNo={self.corp_number}"
        )


class InvoiceApiError(Exception):
    """適格請求書発行事業者公表 API エラー."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(
            f"インボイスAPI エラー ({status_code}): {message}"
        )


# 人格区分コード → ラベル
_KIND_LABELS: dict[str, str] = {
    "1": "個人",
    "2": "法人",
}

# 処理区分コード → ラベル
_PROCESS_LABELS: dict[str, str] = {
    "01": "新規登録",
    "02": "公表内容変更",
    "03": "登録取消",
    "04": "失効",
    "99": "削除",
}
