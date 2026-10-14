"""``redundant-brackets``: brackets that no parse of the term needs. The
``notation`` module's docstring says which."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise

from isar_tools.checks.terms import CLOSERS, OPENERS, argument_end, atom, term_tokens
from isar_tools.source.lexer import Kind, Token
from isar_tools.source.symbols import encode

CODE = "redundant-brackets"
_CONTROL_END = re.compile(r"\\<\^\w+>$")

# Operators of HOL and Pure whose argument slots have priority below 999.
_HOL_OPERATORS = frozenset(
    {
        *("=", "~=", "\\<noteq>", "==", "\\<equiv>", "==>", "\\<Longrightarrow>"),
        *("&", "\\<and>", "|", "\\<or>", "-->", "\\<longrightarrow>"),
        *("<->", "\\<longleftrightarrow>", "~", "\\<not>"),
        *("<", "<=", "\\<le>", ">", ">=", "\\<ge>"),
        *("\\<in>", "\\<notin>", "\\<subseteq>", "\\<subset>", "\\<supseteq>", "\\<supset>"),
        *("\\<union>", "Un", "\\<inter>", "Int", "\\<times>"),
        *("+", "-", "*", "/", "^", "#", "@", "!", "\\<circ>"),
        *("=>", "\\<Rightarrow>"),
    }
)
# Infix words of HOL and its libraries, which an application cannot contain.
_HOL_WORDS = frozenset(
    {
        *("o", "div", "mod", "dvd", "Un", "Int", "O", "OO", "choose", "and", "or", "xor"),
        *("powr", "permutes", "respects", "sums", "within", "has_derivative"),
        *("has_field_derivative", "has_vector_derivative", "has_real_derivative"),
        *("has_integral", "integrable_on", "differentiable", "has_sum", "summable_on"),
    }
)
# Pure's notations whose delimiters include an opening bracket: `TYPE('a)`.
_PURE_WORDS = frozenset({"TYPE", "OFCLASS", "SORT_CONSTRAINT"})
# Words around a slot of priority 0 or 10.
_BEFORE_SLOT = frozenset({"if", "then", "else", "case", "of", "let", "in", "."})
_AFTER_SLOT = frozenset({"then", "else", "of", "in", "::"})
_SEPARATORS = frozenset({",", ";", "|", "\\<lbrakk>", "\\<rbrakk>"})


@dataclass(frozen=True)
class Operators:
    """What the project's notations make of tokens: ``loose`` take an
    application as their argument; ``delimiters`` are part of some notation
    and may take anything."""

    loose: frozenset[str] = frozenset()
    delimiters: frozenset[str] = frozenset()
    opening: frozenset[str] = _PURE_WORDS  # delimiters a notation follows with `(`
    # Some notation follows an argument with `(`: `fun _(_) {_}`.
    after_argument: bool = False

    @classmethod
    def of(cls, infixes: dict[str, int], notations: list[list[list[str]]]) -> "Operators":
        """From the project's infixes, by operator token and priority, and its
        other notations, as the tokens around and between their slots."""
        pieces = [piece for notation in notations for piece in notation]
        low = {op for op, priority in infixes.items() if priority < 999}
        delimiters = {t for piece in pieces for t in piece}
        blocked = delimiters | _PURE_WORDS | {op for op in infixes if op not in low}
        loose = (_HOL_OPERATORS | _HOL_WORDS | low) - blocked
        opening = {a for piece in pieces for a, b in pairwise(piece) if b == "("}
        after = any(piece[:1] == ["("] for notation in notations for piece in notation[1:])
        return cls(
            frozenset(loose),
            frozenset(blocked | low | _HOL_WORDS),
            _PURE_WORDS | opening,
            after,
        )


def _glued(toks: list[Token], i: int, j: int) -> bool:
    return 0 <= j < len(toks) and (toks[j].end == toks[i].start or toks[i].end == toks[j].start)


def _control(toks: list[Token], i: int, j: int) -> bool:
    """Whether ``toks[j]`` is glued to ``toks[i]`` by a control symbol:
    ``\\<^sub>(``, ``x\\<^sub>(``, ``)\\<^sup>``."""
    if not _glued(toks, i, j):
        return False
    return (
        toks[j].text.startswith("\\<^") if j > i else _CONTROL_END.search(toks[j].text) is not None
    )


def _operator(toks: list[Token], k: int, outward: int, ops: Operators) -> bool:
    """Whether ``toks[k]`` is a loose operator on its own: not glued to a
    symbol on the side ``outward`` (-1 or 1) away from the brackets."""
    far = k + outward
    if _glued(toks, k, far) and toks[far].kind in (Kind.SYMBOL, Kind.SYM_IDENT):
        return False
    return encode(toks[k].text) in ops.loose


def _loose_before(toks: list[Token], i: int, ops: Operators) -> bool:
    if i == 0:
        return True
    text = encode(toks[i - 1].text)
    return text in OPENERS | _SEPARATORS | _BEFORE_SLOT or _operator(toks, i - 1, -1, ops)


def _loose_after(toks: list[Token], stop: int, ops: Operators) -> bool:
    if stop == len(toks):
        return True
    text = encode(toks[stop].text)
    return text in CLOSERS | _SEPARATORS | _AFTER_SLOT or _operator(toks, stop, 1, ops)


def _plain(tok: Token, ops: Operators) -> bool:
    return atom(tok) and tok.text != "_" and encode(tok.text) not in ops.delimiters


def _arguments(toks: list[Token], i: int, stop: int, ops: Operators) -> int | None:
    """How many arguments ``toks[i:stop]`` is, or None if it is something
    else: an operator, a notation's delimiter."""
    count = 0
    while i < stop:
        end = argument_end(toks, i)
        if end == i or end > stop or (end == i + 1 and not _plain(toks[i], ops)):
            return None
        i, count = end, count + 1
    return count


def redundant(toks: list[Token], ops: Operators) -> Iterator[tuple[int, int]]:
    """The bracket groups ``toks[i:stop]`` of a term whose brackets can go."""
    i = 0
    while i < len(toks):
        stop = argument_end(toks, i)
        closed = toks[stop - 1].text == ")"
        if toks[i].text != "(" or not closed or stop - i < 3 or _control(toks, i, i - 1):
            i += 1
            continue
        # The brackets may belong to a notation: `TYPE('a)`, `fun f(x) {...}`.
        before = encode(toks[i - 1].text) if i else ""
        argument = i > 0 and (atom(toks[i - 1]) or before in CLOSERS)
        delimited = before in ops.opening or (ops.after_argument and argument)
        if delimited or _control(toks, stop - 1, stop):
            i += 1
            continue
        n = _arguments(toks, i + 1, stop - 1, ops)
        single = n == 1 and (toks[i + 1].text in OPENERS or _plain(toks[i + 1], ops))
        application = (
            n is not None
            and n > 1
            and toks[i + 1].kind is Kind.WORD
            and _loose_before(toks, i, ops)
            and _loose_after(toks, stop, ops)
        )
        if single or application:
            yield i, stop
            # The inner group of `((t))` is judged once the outer one is gone.
            i = stop if single and toks[i + 1].text in OPENERS else i + 1
        else:
            i += 1


def _joins(left: Token, right: Token) -> bool:
    """Whether ``left`` and ``right``, written together, lex as other tokens."""
    return [t.text for t in term_tokens(left.text + right.text)] != [left.text, right.text]


def unbracketed(toks: list[Token], text: str, i: int, stop: int) -> str:
    """``toks[i:stop]`` without its brackets, with a space where it was glued
    to a neighbor it would join."""
    inner = text[toks[i + 1].start : toks[stop - 2].end]
    before = i > 0 and toks[i - 1].end == toks[i].start and _joins(toks[i - 1], toks[i + 1])
    after = (
        stop < len(toks)
        and toks[stop].start == toks[stop - 1].end
        and _joins(toks[stop - 2], toks[stop])
    )
    return (" " if before else "") + inner + (" " if after else "")
