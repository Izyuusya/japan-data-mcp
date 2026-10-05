"""市区町村の地理範囲から XPT002 用の XYZ タイルを求めるユーティリティ.

不動産情報ライブラリの XPT002（地価公示・地価調査ポイントAPI）は
``area``/``city`` を受け付けず、**XYZタイル**（z/x/y）でしか地理を指定できない。
そこで市区町村の代表点を求め、そこを中心にタイル窓を**段階的に広げて飽和を検出**する。

なぜ代表点＋飽和判定か
----------------------
境界ポリゴン（geoshape の N03 GeoJSON 等）はファイル有無が自治体・年度で不安定で、
外部依存にすると取りこぼしや失敗が起きる。代わりに:

1. 国土地理院 住所検索 API（APIキー不要）で市区町村の代表点を取得
2. 代表点のタイルを中心に半径 ``r`` タイルの窓で XPT002 を取得
3. ``r`` を段階的に広げ、**新規地点が増えなくなったら打ち切る**

これで「市域の広さ」に依存せず、必要な範囲を自動で覆える（地点数が飽和＝全域を取得済み）。
市域をまたいで隣接自治体の地点も取得されるが、``city_code`` でフィルタするため問題ない。
"""

from __future__ import annotations

import math
from typing import Any

import httpx

# 国土地理院 住所検索 API（APIキー不要）
GSI_ADDRESS_SEARCH_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"

# 段階拡張の半径（タイル数）。z=13 の1タイルは約4.4km なので、
# r=3 で半径約13km、r=8 で約35km を覆う。
DEFAULT_RADII: tuple[int, ...] = (3, 5, 8, 12)

# タイル数の上限（暴走防止）
DEFAULT_MAX_TILES = 1200


def deg2tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """経緯度を XYZ タイル座標に変換する（Web メルカトル）."""
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int(
        (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
        / 2.0
        * n
    )
    return x, y


def tile_window(
    center_x: int, center_y: int, radius: int, *, max_tiles: int = DEFAULT_MAX_TILES
) -> list[tuple[int, int]]:
    """中心タイルから半径 radius タイルの正方窓を列挙する."""
    size = 2 * radius + 1
    tiles = [
        (x, y)
        for x in range(center_x - radius, center_x + radius + 1)
        for y in range(center_y - radius, center_y + radius + 1)
    ]
    if len(tiles) > max_tiles:
        raise ValueError(
            f"タイル数が多すぎます（{len(tiles)} > {max_tiles}）。"
            "対象地域が広すぎます。用途区分や年で絞ってください。"
        )
    assert len(tiles) == size * size
    return tiles


async def geocode_point(
    client: httpx.AsyncClient, query: str
) -> tuple[float, float] | None:
    """国土地理院 住所検索 API で住所・地域名の代表点（経度, 緯度）を返す."""
    if not query.strip():
        return None
    try:
        resp = await client.get(
            GSI_ADDRESS_SEARCH_URL,
            params={"q": query},
            headers={"Accept-Encoding": "gzip"},
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
    except Exception:
        return None
    if not isinstance(payload, list) or not payload:
        return None
    coords = (payload[0].get("geometry") or {}).get("coordinates")
    if not coords or len(coords) < 2:
        return None
    return float(coords[0]), float(coords[1])


def points_bbox(
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float] | None:
    """座標列の bbox を返す（デバッグ・検証用）."""
    if not points:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return min(lons), min(lats), max(lons), max(lats)
