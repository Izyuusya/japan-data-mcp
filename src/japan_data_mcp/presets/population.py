"""人口データプリセット.

国勢調査・人口推計などから地域の人口データを自動取得し、
整形済みレポートとして返す。

ユーザーは統計表IDを知らなくても、地域名を指定するだけで
人口推移などの情報を取得できる。
都道府県・政令指定都市の両方に対応。
"""

from __future__ import annotations

from dataclasses import dataclass

from japan_data_mcp.estat.client import EStatClient
from japan_data_mcp.estat.formatter import StatsFormatter, build_source_footer
from japan_data_mcp.estat.models import EStatApiError, StatsData, TableInfo

# ------------------------------------------------------------------
# 検索定義: どの統計を探し、どう取得するか
# ------------------------------------------------------------------

# 政府統計コード（安定した識別子）
CENSUS_CODE = "00200521"  # 国勢調査
POPULATION_ESTIMATES_CODE = "00200524"  # 人口推計


@dataclass
class SearchSpec:
    """プリセット用の統計検索定義."""

    label: str  # セクション見出し
    keyword: str  # 検索キーワード
    stats_code: str  # 政府統計コード
    tab_code: str | None = None  # 表章項目フィルタ
    cat01_code: str | None = None  # 分類フィルタ
    limit: int = 100  # データ取得件数上限


# 都道府県レベルの人口ソース（優先順）
POPULATION_SOURCES_PREF: list[SearchSpec] = [
    SearchSpec(
        label="人口推移（人口推計）",
        keyword="人口推計 男女別人口 都道府県",
        stats_code=POPULATION_ESTIMATES_CODE,
    ),
    SearchSpec(
        label="人口推移（国勢調査）",
        keyword="国勢調査 男女別人口 都道府県 全国",
        stats_code=CENSUS_CODE,
    ),
]

# 市区町村レベルの人口ソース（国勢調査のみ対応）
POPULATION_SOURCES_CITY: list[SearchSpec] = [
    SearchSpec(
        label="人口（国勢調査）",
        keyword="国勢調査 男女別人口 市区町村",
        stats_code=CENSUS_CODE,
    ),
    SearchSpec(
        label="人口（国勢調査）",
        keyword="国勢調査 人口等基本集計 市区町村",
        stats_code=CENSUS_CODE,
    ),
]

# 後方互換
POPULATION_SOURCES = POPULATION_SOURCES_PREF


def _is_prefecture_code(area_code: str) -> bool:
    """都道府県コード（末尾 000）かどうか判定する."""
    return area_code.endswith("000")


# ------------------------------------------------------------------
# テーブル選択ロジック
# ------------------------------------------------------------------


def select_table(tables: list[TableInfo]) -> TableInfo | None:
    """検索結果から最適なテーブルを選択する.

    - 小地域テーブルを除外
    - 新しい調査年を優先
    """
    candidates = [t for t in tables if not t.small_area]
    if not candidates:
        candidates = list(tables)
    if not candidates:
        return None

    candidates.sort(key=lambda t: t.survey_date or "", reverse=True)
    return candidates[0]


# ------------------------------------------------------------------
# セクション取得
# ------------------------------------------------------------------


async def fetch_section(
    client: EStatClient,
    spec: SearchSpec,
    area_code: str,
) -> tuple[str, StatsData | None, TableInfo | None]:
    """1セクション分のデータを検索→取得する.

    Returns:
        (セクションラベル, StatsData or None, 使用したTableInfo or None)
    """
    try:
        tables = await client.search_stats(
            spec.keyword,
            stats_code=spec.stats_code,
            limit=5,
        )
    except EStatApiError:
        return spec.label, None, None

    table = select_table(tables)
    if table is None:
        return spec.label, None, None

    try:
        data = await client.get_stats_data(
            table.id,
            cd_area=area_code,
            cd_tab=spec.tab_code,
            cd_cat01=spec.cat01_code,
            limit=spec.limit,
        )
    except EStatApiError:
        return spec.label, None, table

    return spec.label, data, table


def format_section(
    label: str,
    data: StatsData,
    table: TableInfo | None,
    *,
    exclude_dims: set[str] | None = None,
    area_name: str | None = None,
    area_code: str | None = None,
) -> str:
    """取得済みデータを1セクション分のマークダウンに整形する."""
    fmt = StatsFormatter(data)

    lines: list[str] = [f"### {label}"]
    lines.append(fmt.to_markdown(exclude_dims=exclude_dims))
    lines.append(
        build_source_footer(
            table,
            table_id=data.table_id,
            area_name=area_name,
            area_code=area_code,
        )
    )
    return "\n".join(lines)


# ------------------------------------------------------------------
# メイン関数
# ------------------------------------------------------------------


async def fetch_population(
    client: EStatClient,
    area_code: str,
    area_name: str,
) -> str:
    """人口データを検索・取得し、整形済みレポートを返す.

    都道府県コードの場合は人口推計→国勢調査の順で検索。
    市区町村コードの場合は国勢調査の市区町村データを検索。

    Args:
        client: 初期化済みの EStatClient
        area_code: 地域コード（例: "13000", "40130"）
        area_name: 地域名（例: "東京都", "福岡市"）。レポート見出しに使用

    Returns:
        マークダウン形式の人口レポート
    """
    sections: list[str] = [f"## {area_name} の人口データ\n"]

    # 都道府県 or 市区町村でソースを切り替え
    if _is_prefecture_code(area_code):
        sources = POPULATION_SOURCES_PREF
    else:
        sources = POPULATION_SOURCES_CITY

    found = False
    for spec in sources:
        label, data, table = await fetch_section(client, spec, area_code)

        if data is None or not data.values:
            continue

        found = True
        sections.append(
            format_section(
                label,
                data,
                table,
                exclude_dims={"地域"},
                area_name=area_name,
                area_code=area_code,
            )
        )
        # 最初に見つかったソースのデータを採用
        break

    if not found:
        sections.append(
            f"{area_name} の人口データが見つかりませんでした。\n\n"
            "> `search_statistics` で直接検索すると、"
            "より多くの統計表を探せます。"
        )

    return "\n\n".join(sections)
