"""MCP プロトコル経由のエンドツーエンドテスト."""

import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    out = Path("tests/e2e_output.txt")
    lines = []

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "japan_data_mcp"],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                lines.append("=== Session initialized ===\n")

                # 1. resolve_area: 水戸市（市区町村対応の検証）
                lines.append("=== resolve_area('水戸') ===")
                result = await session.call_tool(
                    "resolve_area", {"name": "水戸"}
                )
                for content in result.content:
                    lines.append(content.text)

                # 2. resolve_area: 府中（曖昧地域の検証）
                lines.append("\n=== resolve_area('府中') ===")
                result = await session.call_tool(
                    "resolve_area", {"name": "府中"}
                )
                for content in result.content:
                    lines.append(content.text)

                # 3. compare_regions: 水戸市 vs 宇都宮市 vs 前橋市
                lines.append(
                    "\n=== compare_regions('水戸市', '宇都宮市', '前橋市') ==="
                )
                result = await session.call_tool(
                    "compare_regions",
                    {
                        "stats_data_id": "0003433219",
                        "areas": ["水戸市", "宇都宮市", "前橋市"],
                    },
                )
                for content in result.content:
                    lines.append(content.text)

                # 4. get_regional_data: summary=False（通常モード）
                lines.append(
                    "\n=== get_regional_data('水戸市', summary=False) ==="
                )
                result = await session.call_tool(
                    "get_regional_data",
                    {
                        "stats_data_id": "0003433219",
                        "area": "水戸市",
                    },
                )
                for content in result.content:
                    line_count = content.text.count("\n")
                    lines.append(f"[{line_count} lines returned]")
                    lines.append(content.text[:2000])
                    if len(content.text) > 2000:
                        lines.append("... (truncated)")

                # 5. get_regional_data: summary=True（サマリーモード）
                lines.append(
                    "\n=== get_regional_data('水戸市', summary=True) ==="
                )
                result = await session.call_tool(
                    "get_regional_data",
                    {
                        "stats_data_id": "0003433219",
                        "area": "水戸市",
                        "summary": True,
                    },
                )
                for content in result.content:
                    line_count = content.text.count("\n")
                    lines.append(f"[{line_count} lines returned]")
                    lines.append(content.text)

                # 6. get_population: 水戸市
                lines.append("\n=== get_population('水戸市') ===")
                result = await session.call_tool(
                    "get_population", {"area": "水戸市"}
                )
                for content in result.content:
                    lines.append(content.text)

    except Exception:
        import traceback
        lines.append(traceback.format_exc())

    out.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
