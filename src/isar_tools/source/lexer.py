"""Lossless lexer for Isabelle outer syntax (``.thy`` and ``ROOT`` files).

Every character of the input belongs to exactly one token, so
``"".join(t.text for t in tokenize(s)) == s`` holds for every string ``s``.
Malformed input never raises: an unterminated comment, string, cartouche, or
verbatim block becomes a single ``ERROR`` token running to the end of input.

The token classes follow the outer lexical syntax of the Isabelle/Isar
reference manual. Inner syntax (terms and types inside strings and
cartouches) is not tokenized: those regions are opaque.

Both spellings of cartouche delimiters are accepted: ``\\<open>``/``\\<close>``
and their Unicode renderings ``‹``/``›``.
"""

import re
from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    NEWLINE = "newline"  # "\n", "\r\n", or "\r"
    SPACE = "space"  # horizontal whitespace
    COMMENT = "comment"  # (* ... *), nested
    CARTOUCHE = "cartouche"  # \<open> ... \<close>, nested
    STRING = "string"  # "..."
    ALT_STRING = "alt_string"  # `...`
    VERBATIM = "verbatim"  # {* ... *}
    WORD = "word"  # ident, longident, var, typefree, typevar, nat
    SYM_IDENT = "sym_ident"  # run of symbolic ASCII characters
    SYMBOL = "symbol"  # \<name> that is not a letter, or a non-ASCII character
    DELIM = "delim"  # any other single character, "..", and "::"
    ERROR = "error"  # unterminated region, up to end of input


LAYOUT = frozenset({Kind.NEWLINE, Kind.SPACE})
# Tokens that carry no meaning for the prover: layout and (* *) comments.
IGNORABLE = frozenset({Kind.NEWLINE, Kind.SPACE, Kind.COMMENT})


@dataclass(frozen=True, slots=True)
class Token:
    kind: Kind
    text: str
    start: int

    @property
    def end(self) -> int:
        return self.start + len(self.text)


_GREEK = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "eta",
    "theta",
    "iota",
    "kappa",
    "mu",
    "nu",
    "xi",
    "pi",
    "rho",
    "sigma",
    "tau",
    "upsilon",
    "phi",
    "chi",
    "psi",
    "omega",
    "Gamma",
    "Delta",
    "Theta",
    "Lambda",
    "Xi",
    "Pi",
    "Sigma",
    "Upsilon",
    "Phi",
    "Psi",
    "Omega",
]
# Symbols that count as letters: latin, script and fraktur (\<A>, \<AA>), and
# greek except \<lambda>, which is a binder.
_LETTER = r"(?:[A-Za-z]|\\<(?:[A-Za-z]{1,2}|" + "|".join(_GREEK) + r")>)"
_QUASI = _LETTER + r"|[0-9_']|\\<\^(?:sub|isub|sup|isup|bold)>"
_IDENT = rf"{_LETTER}(?:{_QUASI})*"
_LONG = rf"{_IDENT}(?:\.{_IDENT})*"

_WORD_RE = re.compile(rf"\?'?{_LONG}(?:\.[0-9]+)?|'{_IDENT}|{_LONG}|[0-9]+(?:\.[0-9]+)?")
_NEWLINE_RE = re.compile(r"\r\n|\r|\n")
_SPACE_RE = re.compile(r"[ \t\f\v]+")
_SYM_RE = re.compile(r"[!#$%&*+\-/<=>?@^_|~]+")
_SYMBOL_RE = re.compile(r"\\<\^?[A-Za-z][A-Za-z0-9_']*>")
_COMMENT_DELIM_RE = re.compile(r"\(\*|\*\)")
_CARTOUCHE_DELIM_RE = re.compile(r"\\<open>|\\<close>|‹|›")
_OPEN = ("\\<open>", "‹")


def _nested_end(text: str, pos: int, delims: re.Pattern[str], opens: tuple[str, ...]) -> int:
    """End offset of a nested region whose opener starts at ``pos``, or -1."""
    depth = 0
    for m in delims.finditer(text, pos):
        depth += 1 if m.group(0) in opens else -1
        if depth == 0:
            return m.end()
    return -1


def _quoted_end(text: str, pos: int, quote: str) -> int:
    """End offset of a string starting with ``quote`` at ``pos``, or -1.

    A backslash escapes the following character.
    """
    i = pos + 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
        elif ch == quote:
            return i + 1
        else:
            i += 1
    return -1


def _scan(text: str, pos: int) -> tuple[Kind, int]:
    """Kind and end offset of the token starting at ``pos``."""
    ch = text[pos]
    if ch in "\r\n":
        m = _NEWLINE_RE.match(text, pos)
        assert m is not None
        return Kind.NEWLINE, m.end()
    if m := _SPACE_RE.match(text, pos):
        return Kind.SPACE, m.end()
    if text.startswith("(*", pos):
        end = _nested_end(text, pos, _COMMENT_DELIM_RE, ("(*",))
        return (Kind.COMMENT, end) if end >= 0 else (Kind.ERROR, len(text))
    if text.startswith("{*", pos):
        end = text.find("*}", pos + 2)
        return (Kind.VERBATIM, end + 2) if end >= 0 else (Kind.ERROR, len(text))
    if ch == '"' or ch == "`":
        end = _quoted_end(text, pos, ch)
        if end < 0:
            return Kind.ERROR, len(text)
        return (Kind.STRING if ch == '"' else Kind.ALT_STRING), end
    if text.startswith(_OPEN, pos):
        end = _nested_end(text, pos, _CARTOUCHE_DELIM_RE, _OPEN)
        return (Kind.CARTOUCHE, end) if end >= 0 else (Kind.ERROR, len(text))
    if m := _WORD_RE.match(text, pos):
        return Kind.WORD, m.end()
    if m := _SYMBOL_RE.match(text, pos):
        return Kind.SYMBOL, m.end()
    if m := _SYM_RE.match(text, pos):
        return Kind.SYM_IDENT, m.end()
    if text.startswith(("..", "::"), pos):
        return Kind.DELIM, pos + 2
    if ord(ch) > 127:
        return Kind.SYMBOL, pos + 1
    return Kind.DELIM, pos + 1


def iter_tokens(text: str) -> Iterator[Token]:
    pos = 0
    n = len(text)
    while pos < n:
        kind, end = _scan(text, pos)
        yield Token(kind, text[pos:end], pos)
        pos = end


def tokenize(text: str) -> list[Token]:
    return list(iter_tokens(text))


class LineIndex:
    """Maps 0-based offsets to 1-based line and column numbers.

    Line breaks are ``\\n``, ``\\r\\n``, and ``\\r``, as in the lexer.
    """

    def __init__(self, text: str) -> None:
        self._starts = [0] + [m.end() for m in _NEWLINE_RE.finditer(text)]

    @property
    def line_count(self) -> int:
        return len(self._starts)

    def line(self, offset: int) -> int:
        return bisect_right(self._starts, offset)

    def column(self, offset: int) -> int:
        return offset - self._starts[self.line(offset) - 1] + 1
