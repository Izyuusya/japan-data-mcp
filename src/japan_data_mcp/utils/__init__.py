"""ユーティリティモジュール."""

from japan_data_mcp.utils.area_codes import (
    ALL_AREA_CODES,
    CODE_TO_AREA,
    CODE_TO_PREFECTURE,
    DESIGNATED_CITY_CODES,
    PREFECTURE_CODES,
    resolve_area_code,
)
from japan_data_mcp.utils.field_codes import STATS_FIELD_CODES, list_stats_fields

__all__ = [
    "ALL_AREA_CODES",
    "CODE_TO_AREA",
    "CODE_TO_PREFECTURE",
    "DESIGNATED_CITY_CODES",
    "PREFECTURE_CODES",
    "STATS_FIELD_CODES",
    "list_stats_fields",
    "resolve_area_code",
]
