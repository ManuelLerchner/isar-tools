"""Findings of ``isar check`` and the registry of their codes."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.source.files import read_source
from isar_tools.source.lexer import Kind, LineIndex, tokenize


@dataclass(frozen=True)
class Edit:
    """Replace the text between two offsets of a file."""

    start: int
    end: int
    text: str = ""


@dataclass(frozen=True)
class Fix:
    """The edits that resolve a finding, all or none. A safe fix keeps the
    theory's meaning; an unsafe one should, but only a build can tell."""

    edits: tuple[Edit, ...]
    safe: bool


@dataclass(frozen=True, order=True)
class Finding:
    path: Path
    line: int  # 1-based
    column: int  # 1-based
    code: str
    message: str
    fix: Fix | None = field(default=None, compare=False)

    @classmethod
    def at(
        cls,
        path: Path,
        lines: LineIndex,
        offset: int,
        code: str,
        message: str,
        fix: Fix | None = None,
    ) -> "Finding":
        return cls(path, lines.line(offset), lines.column(offset), code, message, fix)


# code -> (group, description). Codes are stable identifiers for --ignore and
# machine-readable output.
CODES: dict[str, tuple[str, str]] = {
    "root-syntax": ("project", "a ROOT file does not parse"),
    "duplicate-session": ("project", "two sessions have the same name"),
    "missing-theory": ("project", "a theories entry names no existing theory"),
    "missing-directory": ("project", "a session or directories entry names no directory"),
    "theory-path": ("project", "a theories entry is a path, which Isabelle does not load"),
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
    "theory-name": ("syntax", "the header names a theory other than the file, or a qualified one"),
    "invalid-utf8": ("syntax", "a theory file that is not UTF-8"),
    "non-ascii": ("symbols", "a non-ASCII character outside (* *) comments"),
    "undocumented-theory": ("docs", "no text block before a theory's first declaration"),
    "undocumented-heading": ("docs", "a heading with no text block right after or before it"),
    "undocumented-locale": ("docs", "a locale with no text block right before it"),
    "undocumented-class": ("docs", "a type class with no text block right before it"),
    "locale-free-variable": (
        "locales",
        "a locale or context header term names something defined nowhere (heuristic)",
    ),
    "spelled-out-notation": (
        "notation",
        "a constant written out where the project gave it notation or overloading (heuristic)",
    ),
    "spelled-out-abbreviation": (
        "notation",
        "a term written out where the project declared an abbreviation for it (heuristic)",
    ),
    "unused-lemma": ("unused", "a named fact nothing in the project cites (heuristic)"),
    "redundant-import": ("unused", "an import that another import of the theory reaches"),
    "unused-import": ("unused", "an import of which the theory uses nothing (heuristic)"),
    "unused-assumption": (
        "unused",
        "a named locale or class assumption no proof cites (heuristic)",
    ),
    "duplicate-lemma": ("redundant", "a lemma stating another lemma again (heuristic)"),
    "subsumed-lemma": ("redundant", "a lemma that is an instance of another one (heuristic)"),
    "tab": ("hygiene", "a tab character"),
    "carriage-return": ("hygiene", "a carriage return (CRLF or CR line endings)"),
    "bidi-control": ("hygiene", "a bidirectional Unicode control character"),
    "reserved-file-name": ("hygiene", "a file name Windows cannot check out"),
    "empty-modifier": ("methods", "a method modifier such as add: with nothing after it"),
    "duplicate-fact": ("methods", "a fact listed twice after one method modifier"),
    "single-apply": ("methods", "a goal proved by one apply and done instead of by"),
    "proof-search": ("leftovers", "sledgehammer, try, try0, or solve_direct left in"),
    "counterexample-search": ("leftovers", "nitpick, quickcheck, or refute without expect"),
    "goal-reordering": ("leftovers", "defer or prefer reorders the goals"),
    "backtracking": ("leftovers", "back takes another result of the previous method"),
    "diagnostic-command": ("leftovers", "a diagnostic command (thm, print_*, find_theorems, ...)"),
    "retired-identifier": ("retired", "an identifier the project lists as removed comes back"),
    "prose-reference": ("prose", "a plain cartouche in document text names no declaration"),
    "prose-underscore": ("prose", "a raw _ in document text, which LaTeX rejects"),
    "broken-link": ("links", "a link into Isabelle's HTML theories names no page"),
    "broken-anchor": ("links", "a link into Isabelle's HTML theories names no anchor"),
    "anchor-name": ("links", "a theory anchor spells a name other than the theory declares it"),
}

GROUPS = (
    "project",
    "proofs",
    "syntax",
    "symbols",
    "docs",
    "locales",
    "notation",
    "unused",
    "redundant",
    "hygiene",
    "leftovers",
    "methods",
    "retired",
    "prose",
    "links",
)
DEFAULT_GROUPS = ("project", "proofs", "syntax")


# `(* isar-ignore *)`, or `(* isar-ignore: code, code *)` for some codes only.
_IGNORE_RE = re.compile(r"\(\*\s*isar-ignore(?:\s*:\s*([\w\s,-]*?))?\s*\*\)")
# Files whose (* *) comments can carry an ignore comment.
_COMMENTED = ("ROOT", "ROOTS")


def ignore_comments(text: str) -> dict[int, frozenset[str] | None]:
    """Lines an ignore comment covers, with the codes it names (None: every
    code). A comment after code covers its line; a comment alone on its line
    covers the next one."""
    lines = LineIndex(text)
    covered: dict[int, frozenset[str] | None] = {}
    for tok in tokenize(text):
        if tok.kind is not Kind.COMMENT or not (m := _IGNORE_RE.fullmatch(tok.text)):
            continue
        codes = frozenset(c for c in re.split(r"[\s,]+", m.group(1) or "") if c) or None
        line_start = text.rfind("\n", 0, tok.start) + 1
        alone = not text[line_start : tok.start].strip()
        line = lines.line(tok.end - 1) + (1 if alone else 0)
        known = covered.get(line, frozenset())
        covered[line] = None if known is None or codes is None else known | codes
    return covered


def unsuppressed(findings: Iterable[Finding]) -> list[Finding]:
    """``findings`` without the ones an ignore comment covers."""
    covers: dict[Path, dict[int, frozenset[str] | None]] = {}
    kept: list[Finding] = []
    for f in findings:
        if f.path not in covers:
            commented = f.path.suffix == ".thy" or f.path.name in _COMMENTED
            try:
                covers[f.path] = ignore_comments(read_source(f.path)) if commented else {}
            except (OSError, UnicodeDecodeError):
                covers[f.path] = {}
        codes = covers[f.path].get(f.line, frozenset())
        if codes is not None and f.code not in codes:
            kept.append(f)
    return kept
