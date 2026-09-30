"""``retired`` group: identifiers a project has removed on purpose.

Isabelle reads an unknown lowercase identifier in an assumption, a ``fixes``
type, or a theorem statement as a free variable. A locale whose assumption
cites a deleted constant therefore keeps building, and the assumption stops
constraining anything. Nothing in the sources shows it, because the name is
gone from every declaration by then. So the removed names are listed
(``retired`` or ``retired-file`` under ``[check]`` in the configuration, or
``--retired``), and this reports any of them that comes back.

Matching is whole-word, outside ``(* *)`` comments: a retired ``caller_cont``
does not match ``dgs_caller_cont``. The facts Isabelle generates from a name
count as the name itself: ``foo_def``, ``foo_def_raw``, ``foo_axioms``, and
``foo_axioms_def`` (``foo.simps`` matches already).
"""

import re
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.source.lexer import Kind, LineIndex, tokenize

# An identifier, with subscripts as Isabelle writes them (`dep\<^sub>L`).
_WORD = re.compile(r"(?:[A-Za-z0-9_']|\\<\^sub>)+")
# Facts Isabelle derives from a name, longest first.
_SUFFIXES = ("_axioms_def", "_def_raw", "_axioms", "_def")


def read_retired(path: Path) -> list[str]:
    """Names in a list file: one per line; blank lines and ``#`` comments are
    skipped."""
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def check_retired(path: Path, text: str, retired: frozenset[str]) -> list[Finding]:
    # Blank out comments, keeping offsets, so a note about history is fine.
    masked = "".join(
        " " * len(t.text) if t.kind is Kind.COMMENT else t.text for t in tokenize(text)
    )
    lines = LineIndex(text)
    findings: list[Finding] = []
    for m in _WORD.finditer(masked):
        word = m.group(0)
        base = word if word in retired else _base(word, retired)
        if base is not None:
            message = f"{base} is retired" if base == word else f"{word}: {base} is retired"
            findings.append(Finding.at(path, lines, m.start(), "retired-identifier", message))
    return findings


def _base(word: str, retired: frozenset[str]) -> str | None:
    """The retired name ``word`` derives from, as ``foo_def`` from ``foo``."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and word.removesuffix(suffix) in retired:
            return word.removesuffix(suffix)
    return None
