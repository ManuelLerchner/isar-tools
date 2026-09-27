"""Findings of ``isar check`` and the registry of their codes."""

from dataclasses import dataclass
from pathlib import Path

from isar_tools.source.lexer import LineIndex


@dataclass(frozen=True, order=True)
class Finding:
    path: Path
    line: int  # 1-based
    column: int  # 1-based
    code: str
    message: str

    @classmethod
    def at(cls, path: Path, lines: LineIndex, offset: int, code: str, message: str) -> "Finding":
        return cls(path, lines.line(offset), lines.column(offset), code, message)


# code -> (group, description). Codes are stable identifiers for --ignore and
# machine-readable output.
CODES: dict[str, tuple[str, str]] = {
    "root-syntax": ("project", "a ROOT file does not parse"),
    "duplicate-session": ("project", "two sessions have the same name"),
    "missing-theory": ("project", "a theories entry names no existing theory"),
    "missing-directory": ("project", "a session or directories entry names no directory"),
    "missing-document-file": ("project", "a document_files entry names no file"),
    "duplicate-theory-name": (
        "project",
        "two theory files with the same name on one session's search path",
    ),
    "unreached-theory": (
        "project",
        "a theory file on a session's search path that no session builds",
    ),
    "unfinished-proof": ("proofs", "sorry or \\<proof> leaves a goal unproved"),
    "oops": ("proofs", "oops abandons a goal"),
    "unclosed-proof": ("proofs", "a proof does not end before the next theory command"),
    "lexical-error": ("syntax", "an unterminated comment, string, cartouche, or verbatim"),
    "document-argument": ("syntax", "a document command without exactly one text argument"),
    "non-ascii": ("symbols", "a non-ASCII character outside (* *) comments"),
    "undocumented-theory": ("docs", "no text block before a theory's first declaration"),
    "undocumented-heading": ("docs", "a heading with no text block right after or before it"),
    "undocumented-locale": ("docs", "a locale with no text block right before it"),
    "undocumented-class": ("docs", "a type class with no text block right before it"),
    "locale-free-variable": (
        "locales",
        "a locale or context header term names something defined nowhere (heuristic)",
    ),
}

GROUPS = ("project", "proofs", "syntax", "symbols", "docs", "locales")
DEFAULT_GROUPS = ("project", "proofs", "syntax")
