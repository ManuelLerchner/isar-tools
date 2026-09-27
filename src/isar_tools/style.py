"""Terminal colour for human-readable output.

Colour is used only when the output is a terminal, ``NO_COLOR`` is unset, and
``TERM`` is not ``dumb`` (``--color auto``), or when forced with
``--color always``. Machine-readable formats are never coloured.
"""

import argparse
import difflib
import os
from collections.abc import Iterable
from typing import TextIO

_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
}


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    @classmethod
    def for_stream(cls, choice: str, stream: TextIO) -> "Style":
        if choice == "always":
            return cls(True)
        if choice == "never":
            return cls(False)
        terminal = stream.isatty()
        return cls(terminal and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb")

    def __call__(self, text: str, *styles: str) -> str:
        if not self.enabled or not styles:
            return text
        codes = ";".join(_CODES[s] for s in styles)
        return f"\x1b[{codes}m{text}\x1b[0m"


def add_color_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colour human-readable output (default: auto, when writing to a terminal)",
    )


def write_diff(before: str, after: str, name: str, out: TextIO, style: Style) -> None:
    """A unified diff of ``before`` and ``after``, coloured by ``style``."""
    lines: Iterable[str] = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{name}",
        tofile=f"b/{name}",
    )
    for line in lines:
        if line.startswith(("---", "+++")):
            out.write(style(line.rstrip("\r\n"), "bold") + line[len(line.rstrip("\r\n")) :])
        elif line.startswith("@@"):
            out.write(style(line.rstrip("\r\n"), "cyan") + line[len(line.rstrip("\r\n")) :])
        elif line.startswith(("+", "-")):
            color = "green" if line[0] == "+" else "red"
            body = line.rstrip("\r\n")
            out.write(style(body, color) + line[len(body) :])
        else:
            out.write(line)
