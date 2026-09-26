"""Tables and their output formats.

JSON and CSV are machine-readable interfaces: column keys are stable
snake_case names, values are numbers, strings, or booleans. Text and Markdown
are for people and may change.
"""

import csv
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO, TypeAlias

Cell: TypeAlias = str | int | float | bool


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    numeric: bool = False


@dataclass(frozen=True)
class Table:
    name: str  # stable identifier, used as the JSON key
    title: str
    columns: Sequence[Column]
    rows: Sequence[dict[str, Cell]]


def display_path(path: Path) -> str:
    """``path`` relative to the working directory if below it, else absolute,
    with ``/`` separators on every platform so output is stable."""
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _cell(value: Cell) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _text_line(values: Sequence[str], widths: Sequence[int], columns: Sequence[Column]) -> str:
    parts = [
        v.rjust(w) if c.numeric else v.ljust(w)
        for v, w, c in zip(values, widths, columns, strict=True)
    ]
    return "  ".join(parts).rstrip()


def render_text(tables: Sequence[Table], out: TextIO) -> None:
    for index, table in enumerate(tables):
        if index:
            out.write("\n")
        cells = [[_cell(row[c.key]) for c in table.columns] for row in table.rows]
        widths = [len(c.header) for c in table.columns]
        for row in cells:
            widths = [max(w, len(v)) for w, v in zip(widths, row, strict=True)]
        out.write(f"{table.title}\n")
        out.write(_text_line([c.header for c in table.columns], widths, table.columns) + "\n")
        out.write("  ".join("-" * w for w in widths) + "\n")
        for row in cells:
            out.write(_text_line(row, widths, table.columns) + "\n")


def render_markdown(tables: Sequence[Table], out: TextIO) -> None:
    for index, table in enumerate(tables):
        if index:
            out.write("\n")
        out.write(f"### {table.title}\n\n")
        out.write("| " + " | ".join(c.header for c in table.columns) + " |\n")
        out.write("|" + "|".join(" ---: " if c.numeric else " --- " for c in table.columns) + "|\n")
        for row in table.rows:
            values = (_cell(row[c.key]).replace("|", "\\|") for c in table.columns)
            out.write("| " + " | ".join(values) + " |\n")


def render_json(tables: Sequence[Table], out: TextIO) -> None:
    payload = {t.name: [{c.key: row[c.key] for c in t.columns} for row in t.rows] for t in tables}
    json.dump(payload, out, indent=2, ensure_ascii=False)
    out.write("\n")


def render_csv(tables: Sequence[Table], out: TextIO) -> None:
    """One CSV block per table, headed by the table name, blocks separated by a
    blank line. A single table is plain CSV."""
    writer = csv.writer(out, lineterminator="\n")
    for index, table in enumerate(tables):
        if len(tables) > 1:
            if index:
                out.write("\n")
            out.write(f"# {table.name}\n")
        writer.writerow([c.key for c in table.columns])
        for row in table.rows:
            writer.writerow([row[c.key] for c in table.columns])


RENDERERS: dict[str, Callable[[Sequence[Table], TextIO], None]] = {
    "text": render_text,
    "markdown": render_markdown,
    "json": render_json,
    "csv": render_csv,
}
