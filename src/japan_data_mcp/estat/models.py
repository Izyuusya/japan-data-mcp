"""e-Stat APIのデータモデル定義."""

from __future__ import annotations

from pydantic import BaseModel


class TableInfo(BaseModel):
    """統計表のメタ情報."""

    id: str
    stat_name: str
    gov_org: str
    title: str
    survey_date: str | None = None
    open_date: str | None = None
    small_area: bool = False


class ClassItem(BaseModel):
    """分類項目の1要素（コード→名称マッピング）."""

    code: str
    name: str
    level: str | None = None
    unit: str | None = None
    parent_code: str | None = None


class ClassObject(BaseModel):
    """分類オブジェクト（1つの次元のコード体系）."""

    id: str
    name: str
    items: list[ClassItem]


class MetaInfo(BaseModel):
    """統計表のメタ情報（全分類オブジェクト）."""

    table_id: str
    class_objects: list[ClassObject]

    def get_class_object(self, obj_id: str) -> ClassObject | None:
        """IDで分類オブジェクトを取得."""
        for co in self.class_objects:
            if co.id == obj_id:
                return co
        return None

    def resolve_code(self, obj_id: str, code: str) -> str | None:
        """コードを名称に変換（例: area "13000" → "東京都"）."""
        co = self.get_class_object(obj_id)
        if co is None:
            return None
        for item in co.items:
            if item.code == code:
                return item.name
        return None


class DataValue(BaseModel):
    """統計データの1レコード."""

    value: str | None = None
    dimensions: dict[str, str]  # {"tab": "001", "area": "13000", ...}


class StatsData(BaseModel):
    """統計データ取得結果（メタ情報 + データ値）."""

    table_id: str
    meta_info: MetaInfo
    values: list[DataValue]
    total_count: int | None = None


class EStatApiError(Exception):
    """e-Stat APIエラー."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"e-Stat API Error ({status}): {message}")
