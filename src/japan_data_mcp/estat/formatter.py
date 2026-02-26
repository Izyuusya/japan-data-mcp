"""統計データの整形・コード→名称変換モジュール.

e-Stat API が返す生データ（コード番号）を人間が読める名称に自動変換し、
マークダウンテーブルやピボットテーブルなど分析しやすい形に整形する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from japan_data_mcp.estat.models import DataValue, MetaInfo, StatsData, TableInfo

# e-Stat の秘匿・非該当を示す特殊値
_SUPPRESSED_VALUES = frozenset({"-", "***", "…", "x", "X", "*"})


# ------------------------------------------------------------------
# 出力データモデル
# ------------------------------------------------------------------


@dataclass
class FormattedRecord:
    """コード変換・整形済みの1レコード."""

    value: str  # 表示用の値（カンマ区切り数値 or 特殊マーカー）
    numeric_value: float | None  # パース済み数値。非数値なら None
    unit: str | None  # 単位（例: "人", "円"）
    dimensions: dict[str, str]  # {次元名: 名称} e.g. {"地域": "東京都"}


@dataclass
class PivotTable:
    """ピボットテーブル（地域比較・時系列比較に使用）."""

    row_header: str  # 行の次元名（例: "時間軸"）
    col_header: str  # 列の次元名（例: "地域"）
    row_labels: list[str] = field(default_factory=list)
    col_labels: list[str] = field(default_factory=list)
    cells: list[list[str]] = field(default_factory=list)  # cells[row][col]
    unit: str | None = None


# ------------------------------------------------------------------
# メインクラス
# ------------------------------------------------------------------


class StatsFormatter:
    """StatsData のコード→名称変換・整形を行うフォーマッタ.

    Usage::

        fmt = StatsFormatter(stats_data)

        # 全レコードを名称変換
        records = fmt.format_records()

        # マークダウンテーブル
        md = fmt.to_markdown()

        # 地域×時間のピボットテーブル
        md_pivot = fmt.pivot_to_markdown("time", "area")
    """

    def __init__(self, stats_data: StatsData) -> None:
        self._data = stats_data
        self._meta = stats_data.meta_info
        # dimension id → name のマッピング（キャッシュ）
        self._dim_names: dict[str, str] = {
            co.id: co.name for co in self._meta.class_objects
        }

    # ------------------------------------------------------------------
    # レコード変換
    # ------------------------------------------------------------------

    def format_records(
        self,
        *,
        filters: dict[str, str] | None = None,
        limit: int | None = None,
    ) -> list[FormattedRecord]:
        """全レコードのコードを名称に変換して返す.

        Args:
            filters: 絞り込み条件。{次元ID: コード} の辞書。
                     例: ``{"tab": "001"}`` で表章項目を「人口」に限定。
            limit: 返却する最大レコード数。None の場合は全件返却。
        """
        results: list[FormattedRecord] = []
        for dv in self._data.values:
            if filters and not self._matches(dv, filters):
                continue
            results.append(self._format_one(dv))
            if limit is not None and len(results) >= limit:
                break
        return results

    def _format_one(self, dv: DataValue) -> FormattedRecord:
        resolved: dict[str, str] = {}
        for dim_id, code in dv.dimensions.items():
            dim_name = self._dim_names.get(dim_id, dim_id)
            name = self._meta.resolve_code(dim_id, code)
            resolved[dim_name] = name if name is not None else code

        numeric, display = _parse_value(dv.value)
        unit = self._resolve_unit(dv)

        return FormattedRecord(
            value=display,
            numeric_value=numeric,
            unit=unit,
            dimensions=resolved,
        )

    def _resolve_unit(self, dv: DataValue) -> str | None:
        """tab 次元の ClassItem から単位を取得する."""
        tab_code = dv.dimensions.get("tab")
        if tab_code is None:
            return None
        tab_obj = self._meta.get_class_object("tab")
        if tab_obj is None:
            return None
        for item in tab_obj.items:
            if item.code == tab_code:
                return item.unit
        return None

    @staticmethod
    def _matches(dv: DataValue, filters: dict[str, str]) -> bool:
        """DataValue がフィルタ条件にマッチするか判定."""
        for dim_id, code in filters.items():
            if dv.dimensions.get(dim_id) != code:
                return False
        return True

    def latest_time_code(self) -> str | None:
        """データ中の最新の time コードを返す.

        time 次元のコードを文字列ソートし、最大値を返す。
        e-Stat の time コードは ``"2020000000"`` のような形式で、
        文字列ソートで時系列順になる。

        Returns:
            最新の time コード。time 次元がない場合は None。
        """
        time_codes: set[str] = set()
        for dv in self._data.values:
            tc = dv.dimensions.get("time")
            if tc:
                time_codes.add(tc)
        if not time_codes:
            return None
        return max(time_codes)

    def auto_filters_for_pivot(
        self,
        row_dim: str,
        col_dim: str,
        *,
        explicit_filters: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """ピボット用の自動フィルタを構築する.

        row_dim / col_dim 以外の全次元について、
        最初のデータレコードに出現する値で絞り込むフィルタを返す。
        ユーザーが明示指定した次元はそちらを優先する。

        Args:
            row_dim: 行に使う次元ID（例: "time"）
            col_dim: 列に使う次元ID（例: "area"）
            explicit_filters: ユーザーが明示指定したフィルタ

        Returns:
            自動フィルタ辞書（{次元ID: コード}）
        """
        pivot_dims = {row_dim, col_dim}
        extra_dims = [
            co.id for co in self._meta.class_objects if co.id not in pivot_dims
        ]

        if not extra_dims:
            return dict(explicit_filters) if explicit_filters else {}

        # 最初のレコードから各次元の代表値を取得
        filters: dict[str, str] = {}
        if self._data.values:
            first = self._data.values[0]
            for dim_id in extra_dims:
                if dim_id in first.dimensions:
                    filters[dim_id] = first.dimensions[dim_id]

        # ユーザー明示指定で上書き
        if explicit_filters:
            filters.update(explicit_filters)

        return filters

    # ------------------------------------------------------------------
    # マークダウンテーブル出力
    # ------------------------------------------------------------------

    def to_markdown(
        self,
        *,
        filters: dict[str, str] | None = None,
        exclude_dims: set[str] | None = None,
        limit: int | None = None,
    ) -> str:
        """整形済みレコードをマークダウンテーブルに変換.

        Args:
            filters: レコード絞り込み条件（{次元ID: コード}）
            exclude_dims: テーブルから除外する次元名の集合。
                          例: ``{"表章項目"}`` でカラムから除外。
            limit: 表示する最大レコード数。None の場合は全件表示。
        """
        records = self.format_records(filters=filters, limit=limit)
        if not records:
            return "(データなし)"

        exclude = exclude_dims or set()
        dim_keys = [
            k for k in records[0].dimensions if k not in exclude
        ]

        headers = [*dim_keys, "値"]
        rows: list[list[str]] = []
        for rec in records:
            row = [rec.dimensions.get(k, "") for k in dim_keys]
            display = rec.value
            if rec.unit:
                display = f"{display} {rec.unit}"
            row.append(display)
            rows.append(row)

        return _build_markdown_table(headers, rows)

    # ------------------------------------------------------------------
    # ピボットテーブル
    # ------------------------------------------------------------------

    def pivot(
        self,
        row_dim: str,
        col_dim: str,
        *,
        filters: dict[str, str] | None = None,
    ) -> PivotTable:
        """ピボットテーブルを生成する.

        Args:
            row_dim: 行に使う次元ID（例: ``"time"``）
            col_dim: 列に使う次元ID（例: ``"area"``）
            filters: 他の次元での絞り込み条件（{次元ID: コード}）

        Returns:
            PivotTable オブジェクト

        Example::

            # 時間軸を行、地域を列にピボット
            pt = fmt.pivot("time", "area", filters={"tab": "001"})
        """
        records = self.format_records(filters=filters)

        row_name = self._dim_names.get(row_dim, row_dim)
        col_name = self._dim_names.get(col_dim, col_dim)

        # 出現順でユニークラベルを収集
        row_labels: list[str] = []
        col_labels: list[str] = []
        row_seen: set[str] = set()
        col_seen: set[str] = set()

        cell_map: dict[tuple[str, str], str] = {}
        unit: str | None = None

        for rec in records:
            rl = rec.dimensions.get(row_name, "")
            cl = rec.dimensions.get(col_name, "")

            if rl not in row_seen:
                row_labels.append(rl)
                row_seen.add(rl)
            if cl not in col_seen:
                col_labels.append(cl)
                col_seen.add(cl)

            cell_map[(rl, cl)] = rec.value
            if unit is None:
                unit = rec.unit

        cells = [
            [cell_map.get((rl, cl), "") for cl in col_labels]
            for rl in row_labels
        ]

        return PivotTable(
            row_header=row_name,
            col_header=col_name,
            row_labels=row_labels,
            col_labels=col_labels,
            cells=cells,
            unit=unit,
        )

    def pivot_to_markdown(
        self,
        row_dim: str,
        col_dim: str,
        *,
        filters: dict[str, str] | None = None,
    ) -> str:
        """ピボットテーブルをマークダウンテーブル文字列に変換.

        Args:
            row_dim: 行に使う次元ID（例: ``"time"``）
            col_dim: 列に使う次元ID（例: ``"area"``）
            filters: 他の次元での絞り込み条件

        Returns:
            マークダウン形式のテーブル文字列

        Example::

            # 東京都と大阪府の人口を年別に比較
            md = fmt.pivot_to_markdown("time", "area", filters={"tab": "001"})
            # | 時間軸 | 東京都     | 大阪府    |
            # | ---    | ---        | ---       |
            # | 2020年 | 13,960,000 | 8,838,000 |
            # | 2015年 | 13,515,000 | 8,839,000 |
        """
        pt = self.pivot(row_dim, col_dim, filters=filters)

        if not pt.row_labels:
            return "(データなし)"

        unit_suffix = f"（{pt.unit}）" if pt.unit else ""
        header_row = [f"{pt.row_header}{unit_suffix}", *pt.col_labels]

        rows = [
            [rl, *row_cells]
            for rl, row_cells in zip(pt.row_labels, pt.cells)
        ]

        return _build_markdown_table(header_row, rows)


# ------------------------------------------------------------------
# モジュールレベルのヘルパー関数
# ------------------------------------------------------------------


def _parse_value(raw: str | None) -> tuple[float | None, str]:
    """生の値文字列を (数値, 表示文字列) に変換する.

    Returns:
        (numeric_value, display_string) のタプル。
        数値変換できない場合は numeric_value が None。
    """
    if raw is None:
        return None, "-"

    stripped = raw.strip()
    if stripped in _SUPPRESSED_VALUES or stripped == "":
        return None, stripped or "-"

    try:
        numeric = float(stripped)
        if numeric == int(numeric) and "." not in stripped:
            display = f"{int(numeric):,}"
        else:
            display = f"{numeric:,.2f}"
        return numeric, display
    except ValueError:
        return None, stripped


def _build_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """ヘッダーと行データからマークダウンテーブルを構築する."""
    if not headers:
        return ""

    lines: list[str] = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(padded[: len(headers)]) + " |")

    return "\n".join(lines)


# ------------------------------------------------------------------
# データ検証フッター
# ------------------------------------------------------------------

_JST = timezone(timedelta(hours=9))

ESTAT_TABLE_URL = "https://www.e-stat.go.jp/stat-search/database?statdisp_id={table_id}"


def build_source_footer(
    table: TableInfo | None,
    *,
    table_id: str | None = None,
    area_name: str | None = None,
    area_code: str | None = None,
) -> str:
    """データ検証用フッターを生成する.

    出典・検証リンク・検索条件・取得日時・免責注記をまとめたマークダウン文字列を返す。

    Args:
        table: 統計表メタ情報。None の場合は table_id のみで簡易フッターを生成。
        table_id: table が None の場合に使用する統計表ID。
        area_name: データ取得に使用した地域名（検証用）。
        area_code: データ取得に使用した地域コード（検証用）。
    """
    now = datetime.now(_JST).strftime("%Y-%m-%d %H:%M JST")
    tid = table.id if table else (table_id or "")

    lines: list[str] = ["", "---", "**データ検証情報**"]

    if table:
        lines.append(f"- 出典: {table.stat_name}「{table.title}」")
    lines.append(f"- 統計表ID: `{tid}`")

    if tid:
        url = ESTAT_TABLE_URL.format(table_id=tid)
        lines.append(f"- e-Stat で確認: {url}")

    if area_name or area_code:
        area_parts: list[str] = []
        if area_name:
            area_parts.append(area_name)
        if area_code:
            area_parts.append(f"コード: {area_code}")
        lines.append(f"- 検索条件（地域）: {' / '.join(area_parts)}")

    lines.append(f"- データ取得日時: {now}")
    lines.append(
        "- ⚠ 本データは e-Stat API から自動取得した値をそのまま表示しています。"
        "正確性の最終確認は上記リンクから原本データをご参照ください。"
    )
    return "\n".join(lines)
