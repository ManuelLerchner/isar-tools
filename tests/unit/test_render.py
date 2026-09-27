import io

import pytest

from isar_tools.render import RENDERERS, Column, Table
from tests.conftest import Golden

TABLES = [
    Table(
        "first",
        "First table",
        [Column("name", "name"), Column("count", "count", True), Column("ratio", "ratio", True)],
        [
            {"name": "alpha", "count": 3, "ratio": 0.25},
            {"name": "b|eta", "count": 12, "ratio": 1.0},
        ],
    ),
    Table("second", "Second table", [Column("flag", "flag")], [{"flag": True}, {"flag": False}]),
]


@pytest.mark.parametrize("fmt", sorted(RENDERERS))
def test_renderers(fmt: str, golden: Golden) -> None:
    out = io.StringIO()
    RENDERERS[fmt](TABLES, out)
    golden(f"render/two_tables.{fmt}", out.getvalue())


def test_single_table_csv_has_no_heading() -> None:
    out = io.StringIO()
    RENDERERS["csv"](TABLES[1:], out)
    assert out.getvalue() == "flag\nTrue\nFalse\n"
