"""地域総合プロファイル プリセット.

人口・経済など複数分野の統計データを自動取得し、
地域の総合プロファイルとしてまとめて返す。

1回のツール呼び出しで地域の概要を把握できる。
"""

from __future__ import annotations

from japan_data_mcp.estat.client import EStatClient
from japan_data_mcp.estat.models import EStatApiError
from japan_data_mcp.presets.population import (
    SearchSpec,
    fetch_section,
    format_section,
    POPULATION_SOURCES,
)

# ------------------------------------------------------------------
# 経済関連の検索定義
# ------------------------------------------------------------------

# 県民経済計算（内閣府）
_SNA_CODE = "00200502"

ECONOMY_SOURCES: list[SearchSpec] = [
    SearchSpec(
        label="県内総生産（県民経済計算）",
        keyword="県民経済計算 県内総生産",
        stats_code=_SNA_CODE,
        limit=100,
    ),
]

# 労働・雇用
_LABOUR_SURVEY_CODE = "00200531"  # 労働力調査

LABOUR_SOURCES: list[SearchSpec] = [
    SearchSpec(
        label="労働力（労働力調査）",
        keyword="労働力調査 都道府県",
        stats_code=_LABOUR_SURVEY_CODE,
        limit=100,
    ),
]


# ------------------------------------------------------------------
# メイン関数
# ------------------------------------------------------------------


async def fetch_regional_profile(
    client: EStatClient,
    area_code: str,
    area_name: str,
) -> str:
    """地域の総合プロファイルを生成する.

    人口・経済・労働の各分野から統計データを自動取得し、
    1つのレポートにまとめる。各セクションは独立しており、
    一部の取得に失敗しても他のセクションは表示される。

    Args:
        client: 初期化済みの EStatClient
        area_code: 地域コード（例: "13000"）
        area_name: 地域名（例: "東京都"）

    Returns:
        マークダウン形式の地域プロファイル
    """
    report: list[str] = [f"## {area_name} の地域プロファイル\n"]

    # 各分野のデータを取得（失敗してもスキップ）
    source_groups: list[tuple[str, list[SearchSpec]]] = [
        ("人口", POPULATION_SOURCES),
        ("経済", ECONOMY_SOURCES),
        ("労働", LABOUR_SOURCES),
    ]

    found_any = False

    for group_name, sources in source_groups:
        section_found = False
        for spec in sources:
            label, data, table = await fetch_section(
                client, spec, area_code
            )

            if data is None or not data.values:
                continue

            section_found = True
            found_any = True
            report.append(
                format_section(
                    label,
                    data,
                    table,
                    exclude_dims={"地域"},
                    area_name=area_name,
                    area_code=area_code,
                )
            )
            # この分野は最初に見つかったソースで終了
            break

        if not section_found:
            report.append(
                f"### {group_name}\n*{group_name}データは取得できませんでした。*"
            )

    if not found_any:
        report.append(
            f"{area_name} のデータが見つかりませんでした。\n\n"
            "> `search_statistics` で直接検索すると、"
            "より多くの統計表を探せます。"
        )

    report.append(
        "\n---\n"
        "> より詳細なデータは `search_statistics` で統計表を検索し、"
        "`get_regional_data` で取得できます。"
    )

    return "\n\n".join(report)
