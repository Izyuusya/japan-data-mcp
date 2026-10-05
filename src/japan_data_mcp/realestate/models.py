"""不動産取引価格情報 API データモデル."""

from __future__ import annotations

import re

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


class LandPrice(BaseModel):
    """地価公示・地価調査の地点データ（XPT002 のポイントAPIの1地点）.

    地価公示・地価調査は「標準地」の正常な価格（円/㎡）とその属性を返す。
    取引事例（Transaction）とは異なり、所在・最寄駅・規制内容などが
    標準化された形で揃っている。
    """

    point_id: int | None = Field(default=None, alias="point_id")
    """地点ID."""

    target_year_name_ja: str = Field(default="", alias="target_year_name_ja")
    """対象年ラベル（例「令和8年1月1日」）."""

    land_price_type: int | None = Field(default=None, alias="land_price_type")
    """地価区分（0=国土交通省地価公示, 1=都道府県地価調査）."""

    prefecture_code: str = Field(default="", alias="prefecture_code")
    """都道府県コード（2桁）."""

    prefecture_name_ja: str = Field(default="", alias="prefecture_name_ja")
    """都道府県名."""

    city_code: str = Field(default="", alias="city_code")
    """市区町村コード（5桁）."""

    city_county_name_ja: str = Field(default="", alias="city_county_name_ja")
    """市郡名."""

    ward_town_village_name_ja: str = Field(default="", alias="ward_town_village_name_ja")
    """区町村名."""

    use_category_name_ja: str = Field(default="", alias="use_category_name_ja")
    """用途区分名（住宅地/商業地/工業地…）."""

    standard_lot_number_ja: str = Field(default="", alias="standard_lot_number_ja")
    """標準地・基準地番号."""

    place_name_ja: str = Field(default="", alias="place_name_ja")
    """地名."""

    location_number_ja: str = Field(default="", alias="location_number_ja")
    """所在及び地番."""

    u_current_years_price_ja: str = Field(default="", alias="u_current_years_price_ja")
    """当年価格（例「82,300(円/㎡)」）."""

    last_years_price: int | None = Field(default=None, alias="last_years_price")
    """前年価格（円/㎡）."""

    year_on_year_change_rate: str = Field(default="", alias="year_on_year_change_rate")
    """対前年変動率（%、新規地点は空）."""

    u_cadastral_ja: str = Field(default="", alias="u_cadastral_ja")
    """地積（例「537(㎡)」）."""

    nearest_station_name_ja: str = Field(default="", alias="nearest_station_name_ja")
    """最寄駅名."""

    u_road_distance_to_nearest_station_name_ja: str = Field(
        default="", alias="u_road_distance_to_nearest_station_name_ja"
    )
    """最寄駅までの道路距離（例「150m」）."""

    regulations_use_category_name_ja: str = Field(
        default="", alias="regulations_use_category_name_ja"
    )
    """法規制・用途区分（用途地域）."""

    u_regulations_building_coverage_ratio_ja: str = Field(
        default="", alias="u_regulations_building_coverage_ratio_ja"
    )
    """法規制・建蔽率（例「80(%)」）."""

    u_regulations_floor_area_ratio_ja: str = Field(
        default="", alias="u_regulations_floor_area_ratio_ja"
    )
    """法規制・容積率（例「800(%)」）."""

    current_usage_status_of_surrounding_land_name_ja: str = Field(
        default="", alias="current_usage_status_of_surrounding_land_name_ja"
    )
    """周辺の土地の利用現況."""

    model_config = {"populate_by_name": True}

    @property
    def price_int(self) -> int | None:
        """当年価格を整数（円/㎡）で返す。数値化できない場合は None."""
        digits = re.findall(r"[\d,]+", self.u_current_years_price_ja or "")
        if not digits:
            return None
        try:
            return int(digits[0].replace(",", ""))
        except ValueError:
            return None

    @property
    def yoy_rate_float(self) -> float | None:
        """対前年変動率を float で返す。空・数値化不可は None."""
        raw = (self.year_on_year_change_rate or "").replace(",", "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @property
    def price_display(self) -> str:
        """当年価格を「82,300円/㎡」形式で返す."""
        price = self.price_int
        if price is None:
            return self.u_current_years_price_ja or "-"
        return f"{price:,}円/㎡"

    @property
    def land_price_type_display(self) -> str:
        """地価区分を日本語で返す."""
        if self.land_price_type == 0:
            return "国土交通省地価公示"
        if self.land_price_type == 1:
            return "都道府県地価調査"
        return "-"


class RealEstateApiError(Exception):
    """不動産取引価格 API エラー."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"不動産情報ライブラリAPI エラー ({status_code}): {message}")
