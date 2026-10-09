"""The notation a declaration introduces, read off its source.

A document that explains a formalization shows its symbols: ``\\<gamma> a``
for a class parameter ``gamma`` with mixfix ``("\\<gamma>")``, ``a \\<nabla> b``
for ``widen`` with ``(infixl "\\<nabla>" 65)``. Typed by hand, such a table
drifts from the theories. Here a project names the declarations and the
argument names to show; everything else comes from the declaration:

- its shape: a theory-level constant (``definition``, ``fun``, ``inductive``,
  ``abbreviation``, ``consts``, ...), a class parameter, a record field, a
  locale parameter (``fixes`` or ``for``), or an ``abbreviation`` inside a
  locale or class;
- its scope: ``global``, or the locale whose context the notation needs (a
  locale parameter or abbreviation);
- the symbol: the mixfix template with its ``_`` slots filled by the argument
  names, then the remaining arguments applied; without a mixfix, the name
  applied to the arguments;
- the print mode: Isabelle never prints ``abbreviation (input)`` back;
- for an abbreviation, its two sides.

Any other shape (a constant defined inside a locale, a datatype constructor, a
``binder`` or ``structure`` mixfix) is reported as unsupported, never guessed.

A constant without a mixfix may take its notation from ``syntax`` and
``translations``::

    syntax "_rsem" :: "nat \\<Rightarrow> nat \\<Rightarrow> nat set"
      ("\\<gamma>\\<^bsub>_\\<^esub>'(_')")
    translations "\\<gamma>\\<^bsub>v\\<^esub>(r)" == "CONST rsem r v"

The rule's right side applies ``CONST c`` to distinct variables; its left side
applies a syntax constant to the same variables in any order, in the syntax
constant's mixfix or as ``_rsem v r``. Rules with any other pattern are not
followed.
"""

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from itertools import pairwise

from isar_tools.project.hierarchy import bracket_group, parse_mixfix
from isar_tools.project.names import KINDS, Entity
from isar_tools.source.lexer import Kind, Token, tokenize
from isar_tools.source.symbols import decode, encode
from isar_tools.source.theory import significant, unquote

INFIX = frozenset({"infix", "infixl", "infixr"})


class NotationError(ValueError):
    """A declaration whose notation cannot be read off it."""


@dataclass(frozen=True)
class Shape:
    kind: str  # constant, class_parameter, record_field, locale_parameter, locale_abbreviation
    owner: str  # the class, record, or locale declaring it; "" for a constant
    scope: str  # "global", or the locale its notation needs


_CONSTANTS = frozenset(c for c, k in KINDS.items() if k == "constant")


def shape(entity: Entity) -> Shape:
    """What kind of declaration ``entity`` is, as far as its notation goes."""
    command, scope = entity.command, entity.scope
    if entity.kind != "constant":
        raise NotationError(f"a {entity.kind} is not a constant")
    if command == "fixes" and scope.endswith("_class"):
        # A class parameter is a global, overloaded constant `c_class.op`.
        return Shape("class_parameter", scope.removesuffix("_class"), "global")
    if command in ("fixes", "for"):
        return Shape("locale_parameter", scope, scope)
    if command == "record":
        return Shape("record_field", scope, "global")
    if command == "abbreviation" and scope:
        return Shape("locale_abbreviation", scope, scope)
    if command in _CONSTANTS and not entity.member and not scope:
        return Shape("constant", "", "global")
    if command in _CONSTANTS and scope:
        # Outside the locale, the constant takes the locale's parameters first.
        raise NotationError(f"a {command} inside {scope} is not supported")
    raise NotationError(f"a {command} member of {scope} is not supported")


def template(mixfix: str, notation: str) -> str:
    """The notation a mixfix (with its first string ``notation``) writes, with
    ``_`` for each argument slot: ``infixl "+" 65`` is ``_ + _``; "" without a
    mixfix."""
    if not mixfix:
        return ""
    keyword = mixfix.split(maxsplit=1)[0]
    if keyword in INFIX and notation:
        return f"_ {notation} _"
    if keyword in ("binder", "structure") or not notation:
        raise NotationError(f"the mixfix ({mixfix}) is not supported")
    return notation


def _block_end(text: str, i: int) -> int:
    """The index after the block properties following ``(`` at ``i - 1``: a
    priority (``(2``) or a cartouche (``(\\<open>indent=2\\<close>``)."""
    if text.startswith("\\<open>", i):
        close = text.find("\\<close>", i)
        return close + len("\\<close>") if close >= 0 else len(text)
    while i < len(text) and text[i].isdigit():
        i += 1
    return i


def fill(notation: str, name: str, args: list[str]) -> str:
    """``notation`` with its ``_`` slots filled by ``args`` in order and the
    remaining arguments applied after it; ``name`` applied to ``args`` for no
    notation. Blocks, breaks, and quotes are layout, not symbols."""
    if not notation:
        return " ".join([name, *args])
    out: list[str] = []
    rest = list(args)
    i = 0
    while i < len(notation):
        c = notation[i]
        if c == "'" and i + 1 < len(notation):  # quotes the next character
            out.append(notation[i + 1])
            i += 2
        elif notation.startswith("\\<index>", i):
            raise NotationError(f'the structure index in "{notation}" is not supported')
        elif notation.startswith("\\<", i):
            end = notation.find(">", i) + 1 or len(notation)
            out.append(notation[i:end])
            i = end
        elif c == "(":
            i = _block_end(notation, i + 1)
        elif c in ")/":
            i += 1
        elif c == "_":
            if not rest:
                raise NotationError(f'fewer arguments than the slots of "{notation}"')
            out.append(rest.pop(0))
            i += 1
        else:
            out.append(c)
            i += 1
    return " ".join([*"".join(out).split(), *rest])


def display(symbol: str) -> str:
    """``symbol`` with its Isabelle symbols as Unicode, as the editor shows it."""
    return decode(symbol)


_EQUIV = ("\\<equiv>", "≡", "==")


def expansion(statement: str) -> tuple[str, str]:
    """The two sides of ``abbreviation c where "lhs \\<equiv> rhs"``, each on one line."""
    toks = list(significant(tokenize(statement)))
    where = next((i for i, t in enumerate(toks) if t.text == "where"), len(toks))
    specs = [t for t in toks[where + 1 :] if t.kind in (Kind.STRING, Kind.CARTOUCHE)]
    if len(specs) != 1 or len(toks) != where + 2:
        raise NotationError("an abbreviation that is not one `where` equation is not supported")
    body = unquote(specs[0])
    cuts = [(body.find(e), e) for e in _EQUIV if body.count(e) == 1]
    if len(cuts) != 1 or sum(body.count(e) for e in _EQUIV) != 1:
        raise NotationError("an abbreviation not written `lhs \\<equiv> rhs` is not supported")
    at, equiv = cuts[0]
    return " ".join(body[:at].split()), " ".join(body[at + len(equiv) :].split())


_TEXT = frozenset({Kind.STRING, Kind.CARTOUCHE})


@dataclass(frozen=True)
class Syntax:
    """An entry of ``syntax (mode) "_c" :: "type" (mixfix)``."""

    name: str
    mixfix: str
    notation: str
    mode: str  # "" for the default mode, else the print mode: "input", "output", ...


def _mode(args: list[Token]) -> tuple[str, list[Token]]:
    """The print mode ``(input)`` that ``args`` start with, and the rest."""
    if args and args[0].text == "(":
        group, end = bracket_group(args, 0)
        return " ".join(t.text for t in group[1:-1]), args[end:]
    return "", args


def syntax_entries(args: list[Token]) -> Iterator[Syntax]:
    """The entries with a mixfix of a ``syntax`` command, from the tokens after
    its keyword."""
    mode, args = _mode(args)
    for k, tok in enumerate(args):
        if tok.text != "::" or k == 0 or k + 2 >= len(args) or args[k + 2].text != "(":
            continue
        name = unquote(args[k - 1])
        if k > 1 and args[k - 2].text == "_" and args[k - 2].end == args[k - 1].start:
            name = "_" + name  # `_c` lexes as `_`, `c`
        yield Syntax(name, *parse_mixfix(bracket_group(args, k + 2)[0]), mode)


# Rule arrows and the directions they work in: (parse, print).
_ARROWS = {
    "==": (True, True),
    "\\<rightleftharpoons>": (True, True),
    "=>": (True, False),
    "\\<rightharpoonup>": (True, False),
    "<=": (False, True),
    "\\<leftharpoondown>": (False, True),
}


def translation_rules(args: list[Token]) -> Iterator[tuple[str, str, str]]:
    """The rules ``(logic) "lhs" == "rhs"`` of a ``translations`` command, from
    the tokens after its keyword, as (lhs, arrow, rhs)."""
    pats: list[tuple[int, str]] = []  # index of the string, its text
    arrows: dict[int, str] = {}
    for i, tok in enumerate(args):
        if tok.kind in _TEXT:
            pats.append((i, unquote(tok)))
        elif encode(tok.text) in _ARROWS:
            arrows[i] = encode(tok.text)
    for (i, lhs), (j, rhs) in pairwise(pats):
        arrow = next((arrows[k] for k in range(i + 1, j) if k in arrows), "")
        if arrow:
            yield " ".join(lhs.split()), arrow, " ".join(rhs.split())


@dataclass(frozen=True)
class Translation:
    """A translation rule that gives the constant ``constant`` the notation
    of ``syntax``."""

    constant: str  # base name
    parameters: tuple[str, ...]  # the variables of the right side, in its order
    syntax: Syntax
    template: str  # the mixfix's notation with `_` slots
    order: tuple[int, ...]  # the parameter that fills each slot
    lhs: str
    rhs: str
    parse: bool
    print: bool

    def written(self, args: list[str]) -> str:
        """The notation with ``args``, in the constant's order, filled in."""
        n = len(self.parameters)
        if len(args) < n:
            raise NotationError(f"fewer arguments than the slots of {self.lhs}")
        return fill(self.template, "", [*(args[k] for k in self.order), *args[n:]])


def _words(text: str) -> list[Token]:
    return list(significant(tokenize(text)))


def translation(lhs: str, arrow: str, rhs: str, syntax: Mapping[str, Syntax]) -> Translation | None:
    """The notation the rule ``lhs arrow rhs`` gives a constant; None for a rule
    of another shape."""
    right = _words(rhs)
    if len(right) < 2 or right[0].text != "CONST" or right[1].kind is not Kind.WORD:
        return None
    parameters = tuple(t.text for t in right[2:])
    pattern = any(t.kind is not Kind.WORD or t.text[0].isdigit() for t in right[2:])
    if pattern or len(set(parameters)) < len(parameters):
        return None
    constant = right[1].text.rpartition(".")[2]
    toks = _words(lhs)
    left = [t.text for t in toks]
    if len(toks) > 1 and toks[0].text == "_" and toks[1].start == toks[0].end:
        left[:2] = ["_" + left[1]]  # `_c` lexes as `_`, `c`
    applied = bool(left) and left[0] in syntax  # `_c y x`, the syntax constant applied
    for entry in [syntax[left[0]]] if applied else syntax.values():
        written = _template(entry, len(parameters))
        if written is None:
            continue
        if applied:
            slots = tuple(left[1:]) if sorted(left[1:]) == sorted(parameters) else None
        else:
            slots = _slots(lhs, written, parameters)
        if slots is not None:
            order = tuple(parameters.index(v) for v in slots)
            parse, print_ = _ARROWS[arrow]
            return Translation(constant, parameters, entry, written, order, lhs, rhs, parse, print_)
    return None


def _template(entry: Syntax, arity: int) -> str | None:
    """The notation of ``entry``'s mixfix if it has ``arity`` slots that
    ``fill`` can fill."""
    try:
        written = template(entry.mixfix, entry.notation)
        fill(written, "", [""] * arity)
    except NotationError:
        return None
    return written if len(re.findall(r"(?<!')_", written)) == arity else None


def _slots(lhs: str, written: str, parameters: tuple[str, ...]) -> tuple[str, ...] | None:
    """The variables ``lhs`` writes in the slots of the notation ``written``,
    in slot order; None unless it writes each of ``parameters`` once there."""
    marked = fill(written, "", ["\0"] * len(parameters))
    names = "|".join(re.escape(v) for v in sorted(parameters, key=len, reverse=True))
    pieces = [re.escape(p) for p in encode(marked).replace(" ", "").split("\0")]
    found = re.fullmatch(f"({names})".join(pieces), encode(lhs).replace(" ", ""))
    if found is None or sorted(found.groups()) != sorted(parameters):
        return None
    return found.groups()
