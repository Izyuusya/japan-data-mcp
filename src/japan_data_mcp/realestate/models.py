"""不動産取引価格情報 API データモデル."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """不動産取引データ."""

    transaction_type: str = Field(default="", alias="Type")
    """取引種別（宅地(土地と建物), 中古マンション等, 宅地(土地), 林地）."""

    trade_price: str = Field(default="", alias="TradePrice")
    """取引価格（円）."""

    price_per_unit: str = Field(default="", alias="PricePerUnit")
    """坪単価（円）."""

    area: str = Field(default="", alias="Area")
    """面積（㎡）."""

    unit_price: str = Field(default="", alias="UnitPrice")
    """単価（円/㎡）."""

    municipality_code: str = Field(default="", alias="MunicipalityCode")
    """市区町村コード（5桁）."""

    prefecture: str = Field(default="", alias="Prefecture")
    """都道府県名."""

    municipality: str = Field(default="", alias="Municipality")
    """市区町村名."""

    district_name: str = Field(default="", alias="DistrictName")
    """地区名."""

    region: str = Field(default="", alias="Region")
    """地域."""

    floor_plan: str = Field(default="", alias="FloorPlan")
    """間取り."""

    total_floor_area: str = Field(default="", alias="TotalFloorArea")
    """延床面積（㎡）."""

    building_year: str = Field(default="", alias="BuildingYear")
    """建築年."""

    structure: str = Field(default="", alias="Structure")
    """建物構造."""

    use: str = Field(default="", alias="Use")
    """用途."""

    purpose: str = Field(default="", alias="Purpose")
    """今後の利用目的."""

    land_shape: str = Field(default="", alias="LandShape")
    """土地の形状."""

    frontage: str = Field(default="", alias="Frontage")
    """間口（m）."""

    direction: str = Field(default="", alias="Direction")
    """前面道路: 方位."""

    classification: str = Field(default="", alias="Classification")
    """前面道路: 種類."""

    breadth: str = Field(default="", alias="Breadth")
    """前面道路: 幅員（m）."""

    city_planning: str = Field(default="", alias="CityPlanning")
    """都市計画."""

    coverage_ratio: str = Field(default="", alias="CoverageRatio")
    """建ぺい率（%）."""

    floor_area_ratio: str = Field(default="", alias="FloorAreaRatio")
    """容積率（%）."""

    period: str = Field(default="", alias="Period")
    """取引時期（例: "第１四半期"）."""

    renovation: str = Field(default="", alias="Renovation")
    """改装."""

    remarks: str = Field(default="", alias="Remarks")
    """備考."""

    model_config = {"populate_by_name": True}

    @property
    def trade_price_int(self) -> int | None:
        """取引価格を整数で返す."""
        try:
            return int(self.trade_price)
        except (ValueError, TypeError):
            return None

    @property
    def trade_price_display(self) -> str:
        """取引価格を日本円表記で返す（万円）."""
        price = self.trade_price_int
        if price is None:
            return self.trade_price or "-"
        if price >= 100_000_000:
            oku = price // 100_000_000
            man = (price % 100_000_000) // 10_000
            if man:
                return f"{oku}億{man:,}万円"
            return f"{oku}億円"
        if price >= 10_000:
            return f"{price // 10_000:,}万円"
        return f"{price:,}円"


class Municipality(BaseModel):
    """市区町村."""

    code: str = Field(alias="id")
    """市区町村コード（5桁）."""

    name: str = Field(alias="name")
    """市区町村名."""

    model_config = {"populate_by_name": True}


class RealEstateApiError(Exception):
    """不動産取引価格 API エラー."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"不動産情報ライブラリAPI エラー ({status_code}): {message}")
