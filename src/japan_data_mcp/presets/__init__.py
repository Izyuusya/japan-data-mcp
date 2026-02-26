"""プリセットモジュール（よく使う分析パターン）."""

from japan_data_mcp.presets.population import fetch_population
from japan_data_mcp.presets.regional import fetch_regional_profile

__all__ = [
    "fetch_population",
    "fetch_regional_profile",
]
