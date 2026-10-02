"""Inner-syntax terms read lexically: arguments, applications, and patterns.

Without Isabelle's grammar, a term is a token sequence in which an argument
is a name, a literal, or a bracket group. Application associates to the left,
so a name heads an application only when no argument stands before it. A
pattern is a token sequence with variables, each matching one argument, the
same text wherever it occurs.
"""

from collections.abc import Sequence

from isar_tools.checks.locales import TERM_KEYWORDS
from isar_tools.source.lexer import IDENTIFIER_RE, IGNORABLE, Kind, Token, tokenize
from isar_tools.source.symbols import encode

TEXTS = frozenset({Kind.STRING, Kind.CARTOUCHE})
# Infix words of HOL: what follows them is no argument of the name before.
_INFIX_WORDS = frozenset({"o", "div", "mod", "dvd"})
OPENERS = frozenset({"(", "[", "{", "\\<lparr>"})
CLOSERS = frozenset({")", "]", "}", "\\<rparr>"})


def term_tokens(text: str) -> list[Token]:
    return [t for t in tokenize(text) if t.kind not in IGNORABLE]


def spelling(toks: Sequence[Token]) -> list[str]:
    """Token texts with symbols in ASCII, for comparison."""
    return [encode(t.text) for t in toks]


def atom(tok: Token) -> bool:
    """Whether ``tok`` is an argument by itself: a name, a literal, ``_``."""
    if tok.kind is Kind.WORD:
        return tok.text not in TERM_KEYWORDS and tok.text not in _INFIX_WORDS
    return tok.kind in TEXTS or tok.text == "_" or bool(IDENTIFIER_RE.fullmatch(encode(tok.text)))


def heads(toks: Sequence[Token], i: int) -> bool:
    """Whether ``toks[i]`` heads an application: in ``g f x`` the name ``f``
    is an argument of ``g``."""
    return i == 0 or not (atom(toks[i - 1]) or encode(toks[i - 1].text) in CLOSERS)


def argument_end(toks: Sequence[Token], i: int) -> int:
    """The index after the argument starting at ``toks[i]``; ``i`` if none
    starts there. A bracket group is one argument."""
    if i >= len(toks) or not (atom(toks[i]) or encode(toks[i].text) in OPENERS):
        return i
    depth = 0
    while i < len(toks):
        text = encode(toks[i].text)
        depth += (text in OPENERS) - (text in CLOSERS)
        i += 1
        if depth <= 0:
            break
    return i


def arguments(toks: Sequence[Token], i: int) -> int:
    """How many arguments follow at ``toks[i]``."""
    count = 0
    while (end := argument_end(toks, i)) > i:
        i = end
        count += 1
    return count


def match(
    pattern: Sequence[str],
    variables: frozenset[str],
    toks: Sequence[Token],
    spelled: Sequence[str],
    i: int,
    bound: dict[str, tuple[str, ...]] | None = None,
) -> int | None:
    """The index after the instance of ``pattern`` at ``toks[i]``, or None.
    ``spelled`` is ``spelling(toks)``; ``bound`` collects the arguments the
    variables match."""
    bound = {} if bound is None else bound
    for item in pattern:
        if item in variables:
            end = argument_end(toks, i)
            if end == i:
                return None
            value = tuple(spelled[i:end])
            if bound.setdefault(item, value) != value:
                return None
            i = end
        elif i < len(spelled) and spelled[i] == item:
            i += 1
        else:
            return None
    return i


def has_operator(toks: Sequence[Token]) -> bool:
    """Whether ``toks`` has a token outside brackets that is no argument:
    ``a + b``, but not ``f (a + b)``."""
    depth = 0
    for tok in toks:
        text = encode(tok.text)
        if text in OPENERS:
            depth += 1
        elif text in CLOSERS:
            depth -= 1
        elif depth == 0 and not atom(tok):
            return True
    return False


_SEPARATORS = frozenset({",", ";", "|"})


def delimited(toks: Sequence[Token], start: int, end: int) -> bool:
    """Whether ``toks[start:end]`` is a whole term: bracketed, separated, or
    the whole text, so no operator outside can take part of it."""
    before = encode(toks[start - 1].text) if start else ""
    after = encode(toks[end].text) if end < len(toks) else ""
    return (not before or before in OPENERS | _SEPARATORS) and (
        not after or after in CLOSERS | _SEPARATORS
    )
