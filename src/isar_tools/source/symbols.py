"""Isabelle symbols: ``\\<name>`` escapes and their Unicode renderings.

Isabelle source files spell symbols in ASCII (``\\<Longrightarrow>``); the
editor renders them as Unicode (``⟹``). A file saved with the Unicode form
can fail a batch build, so tools convert between the two.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from isar_tools.source.symbol_table import SYMBOLS

# One Isabelle symbol in ASCII form. Control symbols start with ``^``.
SYMBOL_RE = re.compile(r"\\<\^?[A-Za-z][A-Za-z0-9_']*>")

TO_UNICODE: dict[str, str] = {f"\\<{name}>": char for name, char in SYMBOLS.items()}
TO_ASCII: dict[str, str] = {char: escape for escape, char in TO_UNICODE.items()}


def decode(text: str) -> str:
    """Replace every known ``\\<name>`` with its Unicode rendering."""
    return SYMBOL_RE.sub(lambda m: TO_UNICODE.get(m.group(0), m.group(0)), text)


def encode(text: str) -> str:
    """Replace every Unicode rendering of a known symbol with ``\\<name>``."""
    return "".join(TO_ASCII.get(ch, ch) for ch in text)


def symbol_length(text: str) -> int:
    """Length in Isabelle symbols: ``\\<Longrightarrow>`` counts as one."""
    return len(SYMBOL_RE.sub("x", text))


@dataclass(frozen=True)
class NonAscii:
    """A non-ASCII character at a 0-based offset, with its ASCII spelling if any."""

    offset: int
    char: str
    replacement: str | None


def find_non_ascii(text: str) -> Iterator[NonAscii]:
    for offset, ch in enumerate(text):
        if ord(ch) > 127:
            yield NonAscii(offset, ch, TO_ASCII.get(ch))
