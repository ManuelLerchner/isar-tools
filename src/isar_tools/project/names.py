"""Named declarations of a theory: what each command binds, and where.

Read from the command structure, not by pattern matching lines, so a keyword
inside a comment, string, or cartouche never counts. Each entity records

- its base name and kind (``fact``, ``constant``, ``type``, ``locale``,
  ``class``, ``bundle``); the constructors, discriminators, and selectors of a
  datatype and the fields of a record are constants named in the type
  (``t.C``);
- its scope: the locale or class it is declared in, from an ``(in loc)``
  target or the innermost enclosing ``locale``/``class``/``context NAME``
  block that is open (``begin`` ... ``end``); anonymous blocks add nothing;
- its extent: the declaring command and, for a goal, its proof; its statement
  is the command alone, without the ``begin`` of a block it opens;
- its docstring: a ``text`` block directly before it.

The qualified name is ``Theory.scope.name``, as Isabelle's rendered theories
spell it. Names a command derives (``foo_def``, ``foo.simps``) and names made
by interpretations are listed only on request (``derived``).
"""

import textwrap
from collections.abc import Iterator
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

from isar_tools.project.hierarchy import (
    Parameter,
    bracket_group,
    parse_declaration,
    parse_fixes,
    parse_mixfix,
)
from isar_tools.source.keywords import CommandKind
from isar_tools.source.lexer import Kind, Token
from isar_tools.source.theory import Command, Theory, significant, unquote

KINDS: dict[str, str] = {
    **dict.fromkeys(
        [
            "lemma",
            "theorem",
            "corollary",
            "proposition",
            "schematic_goal",
            "lemmas",
            "theorems",
            "named_theorems",
        ],
        "fact",
    ),
    **dict.fromkeys(
        [
            "consts",
            "definition",
            "abbreviation",
            "fun",
            "primrec",
            "function",
            "partial_function",
            "inductive",
            "inductive_set",
            "coinductive",
            "coinductive_set",
            "lift_definition",
            "primcorec",
            "primcorecursive",
            "axiomatization",
        ],
        "constant",
    ),
    **dict.fromkeys(
        [
            "datatype",
            "codatatype",
            "type_synonym",
            "record",
            "typedef",
            "typedecl",
            "quotient_type",
        ],
        "type",
    ),
    "locale": "locale",
    "class": "class",
    "bundle": "bundle",
    "open_bundle": "bundle",
}
# Commands whose name follows type parameters: `datatype ('a, 'b) t`.
_TYPE_PARAMS = frozenset(k for k, v in KINDS.items() if v == "type")
# Commands that open a named scope when followed by `begin`.
_SCOPES = frozenset({"locale", "class", "context"})
# Statement elements: `lemma assumes [simp]: ...` has no name.
_ELEMENTS = frozenset(
    [
        "fixes",
        "assumes",
        "shows",
        "obtains",
        "notes",
        "includes",
        "defines",
        "constrains",
        "if",
        "for",
        "when",
    ]
)
_TEXT = frozenset({Kind.CARTOUCHE, Kind.STRING})


@dataclass(frozen=True)
class Entity:
    name: str
    kind: str
    command: str  # the declaring keyword
    theory: str
    scope: str  # the enclosing locale or class; "" at theory level
    path: Path
    line: int
    end_line: int
    start: int  # text offset where the extent starts (its line's start)
    end: int  # text offset after its last token
    doc: str  # the text block directly before; "" if none
    derived_from: str = ""  # qualified name of the declaration this fact comes from
    # Text offset after the statement: the declaring command without its proof
    # or the `begin` of the block it opens.
    statement_end: int = 0
    # Declared as part of another declaration: a parameter or assumption of a
    # locale, a record field, a datatype constructor or selector.
    member: bool = False
    mixfix: str = ""  # the text inside a constant's mixfix annotation; "" if none
    notation: str = ""  # the first string or cartouche of the mixfix; "" if none
    mode: str = ""  # the syntax mode of `abbreviation (input)`: "input"; "" if none

    @property
    def qualified(self) -> str:
        return ".".join(p for p in (self.theory, self.scope, self.name) if p)


def _skip_group(toks: list[Token], i: int) -> int:
    """Index after the bracket group starting at ``toks[i]``."""
    depth = 0
    while i < len(toks):
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(toks[i].text, 0)
        i += 1
        if depth == 0:
            break
    return i


def _target(toks: list[Token]) -> tuple[str, int]:
    """``(in loc)`` at the start: the locale and the index after it."""
    if len(toks) >= 4 and toks[0].text == "(" and toks[1].text == "in" and toks[3].text == ")":
        return unquote(toks[2]), 4
    return "", 0


def _top(toks: list[Token]) -> Iterator[tuple[int, Token]]:
    """Tokens outside brackets, with their index; brackets are not yielded."""
    depth = 0
    for i, tok in enumerate(toks):
        step = {"(": 1, "[": 1, ")": -1, "]": -1}.get(tok.text, 0)
        depth += step
        if depth == 0 and not step:
            yield i, tok


def _split_top(toks: list[Token], separator: str) -> list[list[Token]]:
    """``toks`` split at ``separator`` outside brackets."""
    cuts = [i for i, t in _top(toks) if t.text == separator and t.kind is not Kind.STRING]
    return [toks[a + 1 : b] for a, b in zip([-1, *cuts], [*cuts, len(toks)], strict=True)]


def _typed(toks: list[Token]) -> list[Parameter]:
    """Constants declared as ``f :: T (mixfix)``, one after another, as in
    ``consts`` and in the body of a record."""
    starts = [i for i, t in _top(toks) if t.kind is Kind.WORD and _follows(toks, i) == "::"]
    ends = [*starts[1:], len(toks)]
    return [p for a, b in zip(starts, ends, strict=True) for p in parse_fixes(toks[a:b])]


def _plain(name: str) -> Parameter:
    return Parameter(name, "", "", "")


def _follows(toks: list[Token], i: int) -> str:
    return toks[i + 1].text if i + 1 < len(toks) else ""


def _names(command: str, toks: list[Token]) -> list[Parameter]:
    """Names bound by ``command`` from its arguments ``toks``, with the type
    and mixfix of a constant."""
    kind = KINDS[command]
    if kind == "fact":
        if not toks or toks[0].kind not in (Kind.WORD, Kind.STRING) or toks[0].text in _ELEMENTS:
            return []
        follow = toks[1].text if len(toks) > 1 else ""
        if command in ("lemmas", "theorems", "named_theorems") or follow in (":", "[", "="):
            return [_plain(unquote(toks[0]))]
        return []
    if kind in ("locale", "class", "bundle"):
        named = toks and toks[0].kind in (Kind.WORD, Kind.STRING)
        return [_plain(unquote(toks[0]))] if named else []
    if command == "consts":  # `consts f :: T g :: U`, without `and`
        return _typed(toks)
    # Parameters (`for r`) and specifications (`where`) follow the names.
    stop = next((j for j, t in enumerate(toks) if t.text in ("where", "for")), len(toks))
    names: list[Parameter] = []
    for part in _split_top(toks[:stop] if kind == "constant" else toks, "and"):
        i = 0
        while i < len(part) and (
            part[i].text == "(" or (command in _TYPE_PARAMS and part[i].text.startswith("'"))
        ):
            i = _skip_group(part, i) if part[i].text == "(" else i + 1
        if i >= len(part) or part[i].kind is not Kind.WORD:
            continue
        follow = part[i + 1].text if i + 1 < len(part) else ""
        if follow in (":", "["):  # a fact name: `definition f_def: "f = ..."`
            continue
        names += parse_fixes(part[i:]) if kind == "constant" else [_plain(part[i].text)]
    return names


def _doc(theory: Theory, command: Command | None) -> str:
    if command is None or command.name != "text":
        return ""
    body = next((t for t in significant(command.tokens(theory.tokens)) if t.kind in _TEXT), None)
    return textwrap.dedent(unquote(body)).strip() if body is not None else ""


# Facts a command derives from the name it binds: suffixes joined with `_` or `.`.
DERIVED: dict[str, tuple[str, ...]] = {
    "definition": ("_def",),
    "lift_definition": ("_def", ".rep_eq", ".transfer"),
    "primrec": (".simps",),
    "fun": (".simps", ".induct", ".cases", ".elims"),
    "function": (".psimps", ".pinduct", ".cases", ".pelims", ".simps", ".induct", ".elims"),
    "inductive": (".intros", ".cases", ".induct", ".simps"),
    "inductive_set": (".intros", ".cases", ".induct", ".simps"),
    "coinductive": (".intros", ".cases", ".coinduct", ".simps"),
    "coinductive_set": (".intros", ".cases", ".coinduct", ".simps"),
    "datatype": (".induct", ".exhaust", ".cases", ".distinct", ".inject", ".simps", ".split"),
    "codatatype": (".coinduct", ".exhaust", ".cases", ".distinct", ".inject", ".simps"),
}
_INDUCTIVE = frozenset({"inductive", "inductive_set", "coinductive", "coinductive_set"})
_INTERPRETATIONS = frozenset({"interpretation", "global_interpretation"})
_DATATYPES = frozenset({"datatype", "codatatype"})


def _record_fields(args: list[Token]) -> list[Parameter]:
    """Fields of ``record 'a r = parent + f :: T g :: U``."""
    eq = next((i for i, t in enumerate(args) if t.text == "="), None)
    return _typed(args[eq + 1 :]) if eq is not None else []


def _constructors(args: list[Token]) -> Iterator[tuple[str, Parameter]]:
    """``(type, constant)`` for the constructors of ``datatype t = is_A: A
    (sel: T) | B (mixfix) and u = C``, their discriminators (``is_A``), and
    their selectors (``sel``)."""
    stop = next((i for i, t in _top(args) if t.text in ("where", "for")), len(args))
    for part in _split_top(args[:stop], "and"):
        eq = next((i for i, t in _top(part) if t.text == "="), len(part))
        # The type's name follows its parameters and the options in brackets.
        head = [t for _, t in _top(part[:eq]) if not t.text.startswith("'")]
        if not head or head[-1].kind is not Kind.WORD:
            continue
        found: dict[str, Parameter] = {}
        for alt in _split_top(part[eq + 1 :], "|"):
            if len(alt) > 2 and alt[1].text == ":":  # a discriminator
                found.setdefault(alt[0].text, _plain(alt[0].text))
                alt = alt[2:]
            if not alt or alt[0].kind is not Kind.WORD:
                continue
            constructor = alt[0].text
            found.setdefault(constructor, _plain(constructor))
            i = 1
            while i < len(alt):
                if alt[i].text != "(":
                    i += 1
                    continue
                group, i = bracket_group(alt, i)
                if len(group) > 3 and group[1].kind is Kind.WORD and group[2].text == ":":
                    found.setdefault(group[1].text, _plain(group[1].text))  # a selector
                else:  # arguments are types, never in brackets: the mixfix
                    found[constructor] = Parameter(constructor, "", *parse_mixfix(group))
        yield from ((head[-1].text, constant) for constant in found.values())


def _rule_names(args: list[Token]) -> list[str]:
    """Names of the rules of an inductive definition: `base: "..." | step: "..."`."""
    stop = next((i for i, t in enumerate(args) if t.text == "where"), None)
    if stop is None:
        return []
    names: list[str] = []
    part: list[Token] = []
    for tok in [*args[stop + 1 :], None]:
        if tok is None or tok.text == "|":
            if len(part) >= 2 and part[0].kind is Kind.WORD and part[1].text in (":", "["):
                names.append(part[0].text)
            part = []
        else:
            part.append(tok)
    return names


def _derived(command: str, bound: str, args: list[Token]) -> list[str]:
    names = [bound + suffix for suffix in DERIVED.get(command, ())]
    if command in _INDUCTIVE:
        names += [f"{bound}.{rule}" for rule in _rule_names(args)]
    if command in ("locale", "class") and any(t.text == "assumes" for t in args):
        names += [f"{bound}_def", f"{bound}.intro"]
        # A locale that extends others gets its own assumptions as `_axioms`.
        if any(t.text == "=" for t in args[:2]) and any(t.text == "+" for t in args):
            names += [f"{bound}_axioms_def", f"{bound}_axioms.intro"]
    return names


@dataclass(frozen=True)
class Interpretation:
    """``interpretation q: loc ...``: loc's facts, qualified by ``q``."""

    qualifier: str
    locale: str
    command: str
    theory: str
    path: Path
    line: int


def interpretations(theory: Theory, name: str, path: Path) -> Iterator[Interpretation]:
    """Qualified theory-level interpretations of ``theory``. Unqualified ones
    and those inside a locale (which extend it) are not followed."""
    depth = 0
    for command in theory.commands:
        args = list(significant(command.tokens(theory.tokens)))[1:]
        if command.kind is CommandKind.THY_END and command.name == "end":
            depth = max(0, depth - 1)
        elif command.kind is CommandKind.THY_DECL_BLOCK and args and args[-1].text == "begin":
            depth += 1
        elif command.name in _INTERPRETATIONS and depth == 0:
            qualifier, expression = _qualifier(args)
            if not qualifier:
                continue
            yield Interpretation(
                qualifier,
                unquote(expression[0]),
                command.name,
                name,
                path,
                theory.lines.line(theory.start(command)),
            )


def interpreted(facts: list[Entity], interpretation: Interpretation) -> Iterator[Entity]:
    """The facts ``interpretation`` makes: every fact declared in its locale
    (not the ones the locale inherits), qualified by its qualifier."""
    locale = interpretation.locale.rpartition(".")[2]
    for fact in facts:
        if fact.kind == "fact" and fact.scope == locale:
            yield Entity(
                name=f"{interpretation.qualifier}.{fact.name}",
                kind="fact",
                command=interpretation.command,
                theory=interpretation.theory,
                scope="",
                path=interpretation.path,
                line=interpretation.line,
                end_line=interpretation.line,
                start=0,
                end=0,
                doc="",
                derived_from=fact.qualified,
            )


def _extent(theory: Theory, commands: list[Command], i: int, stop: int) -> tuple[int, int, int]:
    """The start of the line of ``commands[i]``, the end of its statement,
    and the end of ``commands[i:stop]``, the command with its proof."""
    command = commands[i]
    toks = list(significant(command.tokens(theory.tokens)))
    if command.kind is CommandKind.THY_DECL_BLOCK and len(toks) > 1 and toks[-1].text == "begin":
        statement_end = toks[-2].end
    else:
        statement_end = theory.end(command)
    start = theory.text.rfind("\n", 0, theory.start(command)) + 1
    return start, statement_end, theory.end(commands[stop - 1])


def entities(theory: Theory, name: str, path: Path, derived: bool = False) -> Iterator[Entity]:
    """Every named declaration of ``theory`` (named ``name``, read from
    ``path``); with ``derived``, also the facts the declarations derive
    (``f_def``, ``f.simps``, the rules of an inductive, ...)."""
    stops = {b.statement: b.stop for b in theory.goal_blocks()}
    commands = theory.commands
    for i, command, args, enclosing in _walk(theory):
        if command.name in KINDS:
            target, j = _target(args)
            scope = target or enclosing
            start, statement_end, end = _extent(theory, commands, i, stops.get(i, i + 1))
            mode = _mode(command.name, args[j:])
            for declared in _names(command.name, args[j:]):
                bound = declared.name
                entity = Entity(
                    name=bound,
                    kind=KINDS[command.name],
                    command=command.name,
                    theory=name,
                    scope=scope,
                    path=path,
                    line=theory.lines.line(theory.start(command)),
                    end_line=theory.lines.line(end),
                    start=start,
                    end=end,
                    doc=_doc(theory, commands[i - 1] if i else None),
                    statement_end=statement_end,
                    mixfix=declared.mixfix,
                    notation=declared.notation,
                    mode=mode,
                )
                yield entity
                member = partial(replace, entity, doc="", member=True, mode="")
                # Parameters (`fixes`, and the `for` clause of the parent
                # expression) are constants of the locale, and named
                # assumptions its facts; a class's are named in its `_class`
                # locale: `c_class.op`.
                if command.name in ("locale", "class"):
                    declaration = parse_declaration(theory, command, path)
                    local = bound if command.name == "locale" else f"{bound}_class"
                    fixes = declaration.fixes if declaration else []
                    for_fixes = declaration.for_fixes if declaration else []
                    parameters = [("fixes", p) for p in fixes] + [("for", p) for p in for_fixes]
                    for keyword, p in parameters:
                        yield member(
                            name=p.name,
                            kind="constant",
                            command=keyword,
                            scope=local,
                            mixfix=p.mixfix,
                            notation=p.notation,
                        )
                    for assumption in declaration.assumes if declaration else []:
                        if assumption.name:
                            yield member(
                                name=assumption.name,
                                kind="fact",
                                command="assumes",
                                scope=local,
                                mixfix="",
                                notation="",
                            )
                # Record fields are constants named in the record: `r.field`.
                if command.name == "record":
                    for field in _record_fields(args[j:]):
                        yield member(
                            name=field.name,
                            kind="constant",
                            scope=bound,
                            mixfix=field.mixfix,
                            notation=field.notation,
                        )
                # Constructors, discriminators, and selectors: `t.C`.
                if command.name in _DATATYPES:
                    for type_name, constant in _constructors(args[j:]):
                        if type_name == bound:
                            yield member(
                                name=constant.name,
                                kind="constant",
                                scope=bound,
                                mixfix=constant.mixfix,
                                notation=constant.notation,
                            )
                if derived:
                    for fact in _derived(command.name, bound, args[j:]):
                        yield replace(
                            entity,
                            name=fact,
                            kind="fact",
                            doc="",
                            derived_from=entity.qualified,
                            mixfix="",
                            notation="",
                            mode="",
                        )


def _mode(command: str, args: list[Token]) -> str:
    """The syntax mode of ``abbreviation (input)`` or ``(output)``; "" if none."""
    if command == "abbreviation" and len(args) > 2 and args[0].text == "(" and args[2].text == ")":
        return args[1].text
    return ""


def _walk(theory: Theory) -> Iterator[tuple[int, Command, list[Token], str]]:
    """Each command but ``end`` with its index, its arguments (after
    ``private`` or ``qualified`` and the keyword), and the innermost named
    locale or class block it is in ("" if none)."""
    scopes: list[str] = []  # "" for an anonymous block
    for i, command in enumerate(theory.commands):
        toks = list(significant(command.tokens(theory.tokens)))
        while toks and toks[0].text != command.name:  # `private`, `qualified`
            toks.pop(0)
        args = toks[1:]
        if command.kind is CommandKind.THY_END and command.name == "end":
            if scopes:
                scopes.pop()
            continue
        yield i, command, args, next((s for s in reversed(scopes) if s), "")
        if command.kind is CommandKind.THY_DECL_BLOCK and args and args[-1].text == "begin":
            # `context fixes ... begin` is anonymous; `context loc begin` is not.
            named = command.name in _SCOPES and (command.name != "context" or len(args) == 2)
            scopes.append(unquote(args[0]) if named and len(args) >= 2 else "")


@dataclass(frozen=True)
class Instance:
    """A class instance (``instantiation`` or ``instance t :: c``, ``kind``
    "instance") or a locale interpretation (``interpretation`` or
    ``global_interpretation``, ``kind`` "interpretation"). ``entity`` is its
    source, named ``t :: c`` or by the interpretation's qualifier ("" if it
    has none); ``target`` is the class or locale, and ``arguments`` the text
    of the locale expression after it."""

    target: str
    arguments: str
    entity: Entity

    @property
    def kind(self) -> str:
        return self.entity.kind


_CLASS_INSTANCES = frozenset({"instantiation", "instance"})
# Where the locale expression of an interpretation ends.
_EXPRESSION_END = frozenset({"rewrites", "defines", "for", "begin"})


def _qualifier(args: list[Token]) -> tuple[str, list[Token]]:
    """``q: loc ...``, ``q?: loc ...``: the qualifier and the rest."""
    if len(args) >= 3 and args[0].kind is Kind.WORD and args[1].text in (":", "?:"):
        return args[0].text, args[2:]
    if len(args) >= 4 and args[1].text == "?" and args[2].text == ":":
        return args[0].text, args[3:]
    return "", args


def _instance_heads(
    theory: Theory, command: Command, args: list[Token]
) -> list[tuple[str, str, str]]:
    """``(name, target, arguments)`` of what ``command`` instantiates or
    interprets: one per type of an instantiation, none for a subclass
    ``instance c1 < c2`` or another command."""
    if command.name in _CLASS_INSTANCES:
        colons = next((i for i, t in _top(args) if t.text == "::"), None)
        rest = args[colons + 1 :] if colons is not None else []
        if rest and rest[0].text == "(":  # the sorts of the type's arguments
            rest = rest[_skip_group(rest, 0) :]
        if not rest or rest[0].kind not in (Kind.WORD, Kind.STRING):
            return []
        target = unquote(rest[0])
        types = [unquote(t) for _, t in _top(args[:colons]) if t.text != "and"]
        return [(f"{t} :: {target}", target, "") for t in types]
    qualifier, expression = _qualifier(args)
    if not expression:
        return []
    stop = next(
        (i for i, t in _top(expression) if t.kind is Kind.WORD and t.text in _EXPRESSION_END),
        len(expression),
    )
    rest = expression[1:stop]
    arguments = " ".join(theory.text[rest[0].start : rest[-1].end].split()) if rest else ""
    return [(qualifier, unquote(expression[0]), arguments)]


def instances(theory: Theory, name: str, path: Path) -> Iterator[Instance]:
    """The class instances and locale interpretations of ``theory`` (named
    ``name``, read from ``path``)."""
    stops = {b.statement: b.stop for b in theory.goal_blocks()}
    commands = theory.commands
    for i, command, args, scope in _walk(theory):
        if command.name not in _CLASS_INSTANCES | _INTERPRETATIONS:
            continue
        start, statement_end, end = _extent(theory, commands, i, stops.get(i, i + 1))
        kind = "instance" if command.name in _CLASS_INSTANCES else "interpretation"
        for bound, target, arguments in _instance_heads(theory, command, args):
            entity = Entity(
                name=bound,
                kind=kind,
                command=command.name,
                theory=name,
                scope=scope,
                path=path,
                line=theory.lines.line(theory.start(command)),
                end_line=theory.lines.line(end),
                start=start,
                end=end,
                doc=_doc(theory, commands[i - 1] if i else None),
                statement_end=statement_end,
            )
            yield Instance(target, arguments, entity)


def source(theory: Theory, entity: Entity, statement: bool = False) -> str:
    """The entity's source text, dedented, with ``\\n`` line breaks and one
    final newline, so it does not depend on the line endings of a checkout.
    With ``statement``, only the statement: no proof, and no ``begin``."""
    end = entity.statement_end if statement else entity.end
    text = theory.text[entity.start : end].replace("\r\n", "\n").replace("\r", "\n")
    return textwrap.dedent(text).rstrip() + "\n"


def matches(entity: Entity, name: str) -> bool:
    """Whether ``name`` (``base``, ``scope.base``, ``Theory.base``, or
    ``Theory.scope.base``) refers to ``entity``."""
    spellings = {
        entity.name,
        entity.qualified,
        f"{entity.theory}.{entity.name}",
    }
    if entity.scope:
        spellings.add(f"{entity.scope}.{entity.name}")
    return name in spellings
