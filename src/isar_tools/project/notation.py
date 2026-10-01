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
"""

from dataclasses import dataclass

from isar_tools.project.names import KINDS, Entity
from isar_tools.source.lexer import Kind, tokenize
from isar_tools.source.symbols import decode
from isar_tools.source.theory import significant, unquote


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


def template(entity: Entity) -> str:
    """The notation a mixfix writes, with ``_`` for each argument slot:
    ``infixl "+" 65`` is ``_ + _``; "" without a mixfix."""
    if not entity.mixfix:
        return ""
    keyword = entity.mixfix.split(maxsplit=1)[0]
    if keyword in ("infix", "infixl", "infixr") and entity.notation:
        return f"_ {entity.notation} _"
    if keyword in ("binder", "structure") or not entity.notation:
        raise NotationError(f"the mixfix ({entity.mixfix}) is not supported")
    return entity.notation


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
