"""Class and locale declarations: parents, parameters, and assumptions.

Read from the ``class`` and ``locale`` commands themselves, so a figure or
report built from them cannot drift from the sources. Only declared structure
is extracted:

- ``parents``: the classes or locales a declaration names in its parent
  expression (``class c = order + ...``, ``locale l = a f + b + ...``);
- ``fixes``: parameters with their type and mixfix annotation;
- ``assumes``: named assumptions and their propositions;
- ``for_fixes`` and ``defines``: parameters of the ``for`` clause of the parent
  expression, and local definitions;
- ``terms``: the tokens that hold terms (instance arguments, assumptions,
  definitions), with their source positions;
- ``sorts``: the sorts that type variables of the parameters are constrained
  to (``'a::numeric_domain``); for a class these are superclasses too.

Relationships added later (``sublocale``, ``subclass``, ``interpretation``)
are not followed.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.source.lexer import Kind, Token
from isar_tools.source.theory import Command, Theory, significant, unquote

# `opening` ends a locale expression; its bundles are not elements proper.
_ELEMENTS = frozenset({"fixes", "constrains", "assumes", "defines", "notes", "includes", "opening"})
_TEXT = frozenset({Kind.STRING, Kind.CARTOUCHE})
_TERM = frozenset({Kind.WORD, Kind.STRING, Kind.CARTOUCHE})
# 'a::sort or 'a::{s1, s2} inside a type, possibly with spaces around `::`.
_SORT_RE = re.compile(r"'\w+\s*::\s*(\{[^}]*\}|[A-Za-z_][\w.]*)")


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str  # as written, without quotes; "" if not given
    mixfix: str  # the text inside the annotation's parentheses; "" if none
    notation: str  # the first string or cartouche of the mixfix; "" if none


@dataclass(frozen=True)
class Assumption:
    name: str  # "" if unnamed
    props: tuple[str, ...]


@dataclass
class Declaration:
    kind: str  # "class" or "locale"
    name: str
    path: Path
    line: int
    parents: list[str] = field(default_factory=list[str])
    fixes: list[Parameter] = field(default_factory=list[Parameter])
    assumes: list[Assumption] = field(default_factory=list[Assumption])
    for_fixes: list[Parameter] = field(default_factory=list[Parameter])
    defines: list[Assumption] = field(default_factory=list[Assumption])
    # Term tokens (WORD, STRING, or CARTOUCHE) of the header, in source order;
    # types and mixfix annotations are not terms.
    terms: list[Token] = field(default_factory=list[Token], repr=False)

    @property
    def sorts(self) -> list[str]:
        """Classes that parameter type variables are constrained to, in order."""
        found: dict[str, None] = {}
        for p in self.fixes:
            for m in _SORT_RE.finditer(p.type):
                for sort in m.group(1).strip("{}").split(","):
                    if sort.strip():
                        found.setdefault(sort.strip())
        return list(found)


def _split_top(toks: list[Token], separator: str) -> Iterator[list[Token]]:
    """Split at ``separator`` outside brackets."""
    depth = 0
    part: list[Token] = []
    for tok in toks:
        if tok.kind is Kind.DELIM and tok.text in ("(", "["):
            depth += 1
        elif tok.kind is Kind.DELIM and tok.text in (")", "]"):
            depth -= 1
        if depth == 0 and tok.text == separator and tok.kind is not Kind.STRING:
            yield part
            part = []
        else:
            part.append(tok)
    yield part


def _parents(expression: list[Token]) -> tuple[list[str], list[Token], list[Parameter]]:
    """Names of the classes or locales in a parent expression, the terms of
    their instance arguments, and the parameters of the ``for`` clause."""
    # The `for` clause only renames the instances' parameters.
    stop = next((i for i, t in enumerate(expression) if t.text == "for"), len(expression))
    names: list[str] = []
    terms: list[Token] = []
    for instance in _split_top(expression[:stop], "+"):
        words = list(instance)
        # A qualifier (`q: loc`, `q?: loc`) precedes the locale name.
        if len(words) > 2 and words[1].text in (":", "?:", "?"):
            words = words[3:] if words[1].text == "?" else words[2:]
        if words and words[0].kind in (Kind.WORD, Kind.STRING):
            names.append(unquote(words[0]))
            terms += [t for t in words[1:] if t.kind in _TERM and t.text != "where"]
    for_clause = _split_top(expression[stop + 1 :], "and")
    params = [p for entry in for_clause for p in parse_fixes(entry)]
    return names, terms, params


def parse_mixfix(group: list[Token]) -> tuple[str, str]:
    """A mixfix annotation ``(...)``: its text, and its first string or
    cartouche, the notation."""
    inner = group[1:-1]
    # As written, with each gap between tokens as one space: `[51, 51] 50`.
    text = "".join(
        (" " if i and t.start > inner[i - 1].end else "") + t.text for i, t in enumerate(inner)
    )
    notation = next((unquote(t) for t in inner if t.kind in _TEXT), "")
    return text, notation


def bracket_group(toks: list[Token], i: int) -> tuple[list[Token], int]:
    """The balanced group starting at ``toks[i]`` and the index after it."""
    depth = 0
    j = i
    while j < len(toks):
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(toks[j].text, 0)
        j += 1
        if depth == 0:
            break
    return toks[i:j], j


def parse_fixes(entry: list[Token]) -> Iterator[Parameter]:
    """``x y :: T (mixfix)``: one parameter per name. Also reads the name, type,
    and mixfix of a constant (``definition f :: T (mixfix)``)."""
    names: list[str] = []
    type_ = ""
    mixfix = notation = ""
    i = 0
    while i < len(entry) and entry[i].kind is Kind.WORD:
        names.append(entry[i].text)
        i += 1
    if i < len(entry) and entry[i].text == "::":
        type_ = unquote(entry[i + 1]) if i + 1 < len(entry) else ""
        i += 2
    if i < len(entry) and entry[i].text == "(":
        group, i = bracket_group(entry, i)
        mixfix, notation = parse_mixfix(group)
    for name in names:
        yield Parameter(name, type_, mixfix, notation)


def _assumes(entry: list[Token]) -> tuple[Assumption, list[Token]]:
    """``name [attrs]: "prop" ...`` or just the propositions, and the tokens
    of the propositions (not of ``(is "pattern")``)."""
    name = ""
    i = 0
    if entry and entry[0].kind is Kind.WORD:
        j = 1
        if j < len(entry) and entry[j].text == "[":
            _, j = bracket_group(entry, j)
        if j < len(entry) and entry[j].text == ":":
            name, i = entry[0].text, j + 1
    elif entry and entry[0].text == "[":
        _, j = bracket_group(entry, 0)
        i = j + 1 if j < len(entry) and entry[j].text == ":" else 0
    props = tuple(unquote(t) for t in entry[i:] if t.kind in _TEXT)
    depth = 0
    terms: list[Token] = []
    for tok in entry[i:]:
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(tok.text, 0)
        if depth == 0 and tok.kind in _TEXT:
            terms.append(tok)
    return Assumption(name, props), terms


def _elements(decl: Declaration, body: list[Token]) -> None:
    """Add the context elements (``fixes``, ``assumes``, ...) of ``body``."""
    element = ""
    part: list[Token] = []
    for tok in [*body, None]:
        if tok is None or (tok.kind is Kind.WORD and tok.text in _ELEMENTS):
            for entry in _split_top(part, "and") if element else ():
                if element == "fixes":
                    decl.fixes += parse_fixes(entry)
                elif element in ("assumes", "defines"):
                    assumption, terms = _assumes(entry)
                    (decl.assumes if element == "assumes" else decl.defines).append(assumption)
                    decl.terms += terms
            if tok is not None:
                element, part = tok.text, []
        else:
            part.append(tok)


def _body(toks: list[Token]) -> list[Token]:
    return toks[:-1] if toks and toks[-1].text == "begin" else toks


def parse_declaration(theory: Theory, command: Command, path: Path) -> Declaration | None:
    """The declaration made by a ``class`` or ``locale`` command, or None."""
    if command.name not in ("class", "locale"):
        return None
    toks = list(significant(command.tokens(theory.tokens)))[1:]
    if not toks or toks[0].kind not in (Kind.WORD, Kind.STRING):
        return None
    decl = Declaration(
        command.name, unquote(toks[0]), path, theory.lines.line(theory.start(command))
    )
    body = _body(toks[2:] if len(toks) > 1 and toks[1].text == "=" else [])
    first = next(
        (i for i, t in enumerate(body) if t.kind is Kind.WORD and t.text in _ELEMENTS),
        len(body),
    )
    expression = body[:first]
    if expression and expression[-1].text == "+":
        expression = expression[:-1]
    decl.parents, decl.terms, decl.for_fixes = _parents(expression)
    _elements(decl, body[first:])
    return decl


def parse_context(theory: Theory, command: Command, path: Path) -> Declaration | None:
    """The block a ``context`` command opens, as a declaration of kind
    ``context``: ``context loc begin`` has the parent ``loc``; an unnamed
    ``context fixes ... assumes ... begin`` has its own elements."""
    if command.name != "context":
        return None
    toks = _body(list(significant(command.tokens(theory.tokens)))[1:])
    decl = Declaration("context", "", path, theory.lines.line(theory.start(command)))
    if toks and toks[0].kind in (Kind.WORD, Kind.STRING) and toks[0].text not in _ELEMENTS:
        decl.parents = [unquote(toks[0])]
        toks = toks[1:]
    _elements(decl, toks)
    return decl


def declarations(theory: Theory, path: Path) -> Iterator[Declaration]:
    for command in theory.commands:
        decl = parse_declaration(theory, command, path)
        if decl is not None:
            yield decl


@dataclass(frozen=True)
class Located:
    """A declaration with the session that owns its theory."""

    decl: Declaration
    session: str
    external: bool  # from an included (-d) directory


def extends(located: Located) -> list[str]:
    """Names a declaration extends: its parents and, for a class, the sorts of
    its type variable (superclasses in Isabelle's sense)."""
    decl = located.decl
    extra = decl.sorts if decl.kind == "class" else []
    return list(dict.fromkeys([*decl.parents, *extra]))


Visible = Callable[[Path], set[Path]]


def resolve(
    index: dict[str, list[Located]], name: str, visible: set[Path] | None = None
) -> Located | None:
    """The declaration a (possibly theory-qualified) name refers to.

    With ``visible``, only declarations in those theory files count: a parent
    name refers to what the declaring theory imports, never to an unrelated
    declaration of the same name elsewhere. Without it (a name given by the
    user), declarations of the project win over included ones.
    """
    candidates = index.get(name.rpartition(".")[2], [])
    if visible is not None:
        candidates = [c for c in candidates if c.decl.path in visible]
    own = [c for c in candidates if not c.external]
    return (own or candidates or [None])[0]


def closure(
    index: dict[str, list[Located]],
    roots: list[str],
    visible: Visible,
    context: Path | None = None,
) -> tuple[list[Located], list[str]]:
    """``roots`` and everything they extend, parents before children, and the
    names that no visible declaration defines. ``visible(path)`` is the set of
    theory files a theory can see: itself and its imports. With ``context``,
    the roots are names as written in that theory file."""
    ordered: list[Located] = []
    seen: set[int] = set()
    missing: dict[str, None] = {}

    def visit(name: str, context: Path | None, active: frozenset[int]) -> None:
        found = resolve(index, name, visible(context) if context is not None else None)
        if found is None:
            missing.setdefault(name)
            return
        key = id(found)
        if key in seen or key in active:
            return
        for parent in extends(found):
            visit(parent, found.decl.path, active | {key})
        seen.add(key)
        ordered.append(found)

    for root in roots:
        visit(root, context, frozenset())
    return ordered, list(missing)


def _parameters_json(parameters: list[Parameter]) -> list[dict[str, str]]:
    return [
        {"name": p.name, "type": p.type, "mixfix": p.mixfix, "notation": p.notation}
        for p in parameters
    ]


def as_json(located: Located, display: str) -> dict[str, object]:
    decl = located.decl
    return {
        "kind": decl.kind,
        "name": decl.name,
        "session": located.session,
        "external": located.external,
        "path": display,
        "line": decl.line,
        "parents": decl.parents,
        "sorts": decl.sorts,
        "fixes": _parameters_json(decl.fixes),
        "for_fixes": _parameters_json(decl.for_fixes),
        "assumes": [{"name": a.name, "props": list(a.props)} for a in decl.assumes],
    }
