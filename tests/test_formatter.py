"""StatsFormatter のユニットテスト."""

import pytest

from japan_data_mcp.estat.formatter import (
    FormattedRecord,
    StatsFormatter,
    _parse_value,
)
from japan_data_mcp.estat.models import (
    ClassItem,
    ClassObject,
    DataValue,
    MetaInfo,
    StatsData,
)


# ------------------------------------------------------------------
# テスト用データ
# ------------------------------------------------------------------


def _make_stats_data(
    values: list[DataValue] | None = None,
) -> StatsData:
    """テスト用の StatsData を構築."""
    meta = MetaInfo(
        table_id="TEST001",
        class_objects=[
            ClassObject(
                id="tab",
                name="表章項目",
                items=[
                    ClassItem(code="001", name="人口", unit="人"),
                    ClassItem(code="002", name="世帯数", unit="世帯"),
                ],
            ),
            ClassObject(
                id="area",
                name="地域",
                items=[
                    ClassItem(code="13000", name="東京都"),
                    ClassItem(code="27000", name="大阪府"),
                    ClassItem(code="23000", name="愛知県"),
                ],
            ),
            ClassObject(
                id="time",
                name="時間軸",
                items=[
                    ClassItem(code="2020000000", name="2020年"),
                    ClassItem(code="2015000000", name="2015年"),
                ],
            ),
        ],
    )
    if values is None:
        values = [
            DataValue(
                value="13960000",
                dimensions={
                    "tab": "001",
                    "area": "13000",
                    "time": "2020000000",
                },
            ),
            DataValue(
                value="8838000",
                dimensions={
                    "tab": "001",
                    "area": "27000",
                    "time": "2020000000",
                },
            ),
            DataValue(
                value="13515000",
                dimensions={
                    "tab": "001",
                    "area": "13000",
                    "time": "2015000000",
                },
            ),
            DataValue(
                value="8839000",
                dimensions={
                    "tab": "001",
                    "area": "27000",
                    "time": "2015000000",
                },
            ),
        ]
    return StatsData(
        table_id="TEST001",
        meta_info=meta,
        values=values,
        total_count=len(values),
    )


# ------------------------------------------------------------------
# _parse_value
# ------------------------------------------------------------------


class TestParseValue:
    def test_integer(self):
        num, display = _parse_value("13960000")
        assert num == 13960000.0
        assert display == "13,960,000"

    def test_float(self):
        num, display = _parse_value("3.14")
        assert num == pytest.approx(3.14)
        assert display == "3.14"

    def test_none(self):
        num, display = _parse_value(None)
        assert num is None
        assert display == "-"

    def test_suppressed_triple_star(self):
        num, display = _parse_value("***")
        assert num is None
        assert display == "***"

    def test_suppressed_dash(self):
        num, display = _parse_value("-")
        assert num is None
        assert display == "-"

    def test_suppressed_ellipsis(self):
        num, display = _parse_value("…")
        assert num is None
        assert display == "…"

    def test_empty_string(self):
        num, display = _parse_value("")
        assert num is None
        assert display == "-"

    def test_non_numeric_string(self):
        num, display = _parse_value("該当なし")
        assert num is None
        assert display == "該当なし"

    def test_negative_number(self):
        num, display = _parse_value("-500")
        assert num == -500.0
        assert display == "-500"


# ------------------------------------------------------------------
# format_records
# ------------------------------------------------------------------


class TestFormatRecords:
    def test_basic_format(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        records = fmt.format_records()

        assert len(records) == 4

        r0 = records[0]
        assert r0.value == "13,960,000"
        assert r0.numeric_value == 13960000.0
        assert r0.unit == "人"
        assert r0.dimensions["地域"] == "東京都"
        assert r0.dimensions["時間軸"] == "2020年"
        assert r0.dimensions["表章項目"] == "人口"

    def test_unknown_code_falls_back_to_code(self):
        """メタ情報にないコードはコード文字列のまま返す."""
        values = [
            DataValue(
                value="100",
                dimensions={"tab": "001", "area": "99999", "time": "2020000000"},
            )
        ]
        data = _make_stats_data(values)
        fmt = StatsFormatter(data)
        records = fmt.format_records()

        assert records[0].dimensions["地域"] == "99999"

    def test_filter_by_tab(self):
        values = [
            DataValue(
                value="100",
                dimensions={"tab": "001", "area": "13000", "time": "2020000000"},
            ),
            DataValue(
                value="50",
                dimensions={"tab": "002", "area": "13000", "time": "2020000000"},
            ),
        ]
        data = _make_stats_data(values)
        fmt = StatsFormatter(data)

        # tab=001（人口）のみ
        records = fmt.format_records(filters={"tab": "001"})
        assert len(records) == 1
        assert records[0].dimensions["表章項目"] == "人口"

    def test_unit_resolved_from_tab(self):
        values = [
            DataValue(
                value="50",
                dimensions={"tab": "002", "area": "13000", "time": "2020000000"},
            ),
        ]
        data = _make_stats_data(values)
        fmt = StatsFormatter(data)
        records = fmt.format_records()

        assert records[0].unit == "世帯"

    def test_suppressed_value(self):
        values = [
            DataValue(
                value="***",
                dimensions={"tab": "001", "area": "13000", "time": "2020000000"},
            ),
        ]
        data = _make_stats_data(values)
        fmt = StatsFormatter(data)
        records = fmt.format_records()

        assert records[0].value == "***"
        assert records[0].numeric_value is None


# ------------------------------------------------------------------
# to_markdown
# ------------------------------------------------------------------


class TestToMarkdown:
    def test_basic_table(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        md = fmt.to_markdown()

        lines = md.strip().split("\n")
        assert len(lines) == 6  # header + separator + 4 data rows
        assert "表章項目" in lines[0]
        assert "地域" in lines[0]
        assert "時間軸" in lines[0]
        assert "値" in lines[0]
        assert "東京都" in lines[2]
        assert "13,960,000" in lines[2]

    def test_exclude_dims(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        md = fmt.to_markdown(exclude_dims={"表章項目"})

        lines = md.strip().split("\n")
        assert "表章項目" not in lines[0]
        assert "地域" in lines[0]

    def test_unit_in_value_column(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        md = fmt.to_markdown()

        # 人 が値の横に付く
        assert "人" in md

    def test_empty_data(self):
        data = _make_stats_data(values=[])
        fmt = StatsFormatter(data)
        md = fmt.to_markdown()

        assert md == "(データなし)"

    def test_filter_in_markdown(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)

        # 東京都のみ
        md = fmt.to_markdown(filters={"area": "13000"})
        assert "東京都" in md
        assert "大阪府" not in md


# ------------------------------------------------------------------
# pivot / pivot_to_markdown
# ------------------------------------------------------------------


class TestPivot:
    def test_time_by_area(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        pt = fmt.pivot("time", "area")

        assert pt.row_header == "時間軸"
        assert pt.col_header == "地域"
        assert pt.row_labels == ["2020年", "2015年"]
        assert pt.col_labels == ["東京都", "大阪府"]
        assert pt.unit == "人"

        # cells[0] = 2020年の行
        assert pt.cells[0][0] == "13,960,000"  # 東京都 2020年
        assert pt.cells[0][1] == "8,838,000"  # 大阪府 2020年
        assert pt.cells[1][0] == "13,515,000"  # 東京都 2015年
        assert pt.cells[1][1] == "8,839,000"  # 大阪府 2015年

    def test_area_by_time(self):
        """行列を入れ替えても正しく動く."""
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        pt = fmt.pivot("area", "time")

        assert pt.row_header == "地域"
        assert pt.col_header == "時間軸"
        assert pt.row_labels == ["東京都", "大阪府"]
        assert pt.col_labels == ["2020年", "2015年"]

    def test_pivot_with_filter(self):
        """3地域のデータからフィルタして2地域だけピボット."""
        values = [
            DataValue(
                value="13960000",
                dimensions={"tab": "001", "area": "13000", "time": "2020000000"},
            ),
            DataValue(
                value="8838000",
                dimensions={"tab": "001", "area": "27000", "time": "2020000000"},
            ),
            DataValue(
                value="7542000",
                dimensions={"tab": "001", "area": "23000", "time": "2020000000"},
            ),
        ]
        data = _make_stats_data(values)
        fmt = StatsFormatter(data)

        # tab=001 でフィルタ（全部 001 だが、動作確認）
        pt = fmt.pivot("time", "area", filters={"tab": "001"})
        assert len(pt.col_labels) == 3
        assert "愛知県" in pt.col_labels

    def test_missing_cell_is_empty(self):
        """一部の組み合わせにデータがない場合、空文字になる."""
        values = [
            DataValue(
                value="13960000",
                dimensions={"tab": "001", "area": "13000", "time": "2020000000"},
            ),
            # 大阪府 2020年 のデータなし
            DataValue(
                value="13515000",
                dimensions={"tab": "001", "area": "13000", "time": "2015000000"},
            ),
            DataValue(
                value="8839000",
                dimensions={"tab": "001", "area": "27000", "time": "2015000000"},
            ),
        ]
        data = _make_stats_data(values)
        fmt = StatsFormatter(data)
        pt = fmt.pivot("time", "area")

        # 大阪府 2020年 は空
        osaka_col = pt.col_labels.index("大阪府")
        assert pt.cells[0][osaka_col] == ""
        # 大阪府 2015年 は値あり
        assert pt.cells[1][osaka_col] == "8,839,000"

    def test_pivot_to_markdown(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        md = fmt.pivot_to_markdown("time", "area")

        lines = md.strip().split("\n")
        assert len(lines) == 4  # header + separator + 2 rows

        # ヘッダーに単位付き行名と地域名
        assert "時間軸（人）" in lines[0]
        assert "東京都" in lines[0]
        assert "大阪府" in lines[0]

        # データ行
        assert "2020年" in lines[2]
        assert "13,960,000" in lines[2]

    def test_pivot_to_markdown_empty(self):
        data = _make_stats_data(values=[])
        fmt = StatsFormatter(data)
        md = fmt.pivot_to_markdown("time", "area")
        assert md == "(データなし)"


# ------------------------------------------------------------------
# latest_time_code
# ------------------------------------------------------------------


class TestLatestTimeCode:
    def test_returns_latest(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        assert fmt.latest_time_code() == "2020000000"

    def test_no_time_dimension(self):
        """time 次元がないデータでは None を返す."""
        meta = MetaInfo(
            table_id="TEST",
            class_objects=[
                ClassObject(
                    id="tab",
                    name="表章項目",
                    items=[ClassItem(code="001", name="人口", unit="人")],
                ),
            ],
        )
        values = [DataValue(value="100", dimensions={"tab": "001"})]
        data = StatsData(
            table_id="TEST", meta_info=meta, values=values, total_count=1
        )
        fmt = StatsFormatter(data)
        assert fmt.latest_time_code() is None

    def test_empty_data(self):
        data = _make_stats_data(values=[])
        fmt = StatsFormatter(data)
        assert fmt.latest_time_code() is None


# ------------------------------------------------------------------
# format_records / to_markdown with limit
# ------------------------------------------------------------------


class TestLimit:
    def test_format_records_limit(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        all_records = fmt.format_records()
        limited = fmt.format_records(limit=2)
        assert len(all_records) == 4
        assert len(limited) == 2

    def test_to_markdown_limit(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)

        # limit=1 なら表のデータ行は1行だけ
        md = fmt.to_markdown(limit=1)
        lines = md.strip().split("\n")
        # header + separator + 1 data row = 3 lines
        assert len(lines) == 3

    def test_limit_none_returns_all(self):
        data = _make_stats_data()
        fmt = StatsFormatter(data)
        records = fmt.format_records(limit=None)
        assert len(records) == 4
