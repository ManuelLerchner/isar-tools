"""Named declarations of a theory: what each command binds, and where.

Read from the command structure, not by pattern matching lines, so a keyword
inside a comment, string, or cartouche never counts. Each entity records

- its base name and kind (``fact``, ``constant``, ``type``, ``locale``,
  ``class``, ``bundle``);
- its scope: the locale or class it is declared in, from an ``(in loc)``
  target or the innermost enclosing ``locale``/``class``/``context NAME``
  block that is open (``begin`` ... ``end``); anonymous blocks add nothing;
- its extent: the declaring command and, for a goal, its proof;
- its docstring: a ``text`` block directly before it.

The qualified name is ``Theory.scope.name``, as Isabelle's rendered theories
spell it. Names a command derives (``foo_def``, ``foo.simps``) and names made
by interpretations are not listed.
"""

import textwrap
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from isar_tools.project.hierarchy import parse_declaration
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


def _split_and(toks: list[Token]) -> Iterator[list[Token]]:
    depth = 0
    part: list[Token] = []
    for tok in toks:
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(tok.text, 0)
        if depth == 0 and tok.kind is Kind.WORD and tok.text == "and":
            yield part
            part = []
        else:
            part.append(tok)
    yield part


def _names(command: str, toks: list[Token]) -> list[str]:
    """Names bound by ``command`` from its arguments ``toks``."""
    kind = KINDS[command]
    if kind == "fact":
        if not toks or toks[0].kind not in (Kind.WORD, Kind.STRING) or toks[0].text in _ELEMENTS:
            return []
        follow = toks[1].text if len(toks) > 1 else ""
        if command in ("lemmas", "theorems", "named_theorems") or follow in (":", "[", "="):
            return [unquote(toks[0])]
        return []
    if kind in ("locale", "class", "bundle"):
        return [unquote(toks[0])] if toks and toks[0].kind in (Kind.WORD, Kind.STRING) else []
    # Parameters (`for r`) and specifications (`where`) follow the names.
    stop = next((j for j, t in enumerate(toks) if t.text in ("where", "for")), len(toks))
    names: list[str] = []
    for part in _split_and(toks[:stop] if kind == "constant" else toks):
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
        names.append(part[i].text)
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


def _record_fields(args: list[Token]) -> list[str]:
    """Fields of ``record 'a r = parent + f :: T g :: U``: words before ``::``
    at bracket depth 0, after the ``=``."""
    eq = next((i for i, t in enumerate(args) if t.text == "="), None)
    if eq is None:
        return []
    fields: list[str] = []
    depth = 0
    body = args[eq + 1 :]
    for i, tok in enumerate(body):
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(tok.text, 0)
        following = body[i + 1].text if i + 1 < len(body) else ""
        if depth == 0 and tok.kind is Kind.WORD and following == "::":
            fields.append(tok.text)
    return fields


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
            if len(args) >= 3 and args[0].kind is Kind.WORD and args[1].text in (":", "?:"):
                locale = args[2]
            elif len(args) >= 4 and args[1].text == "?" and args[2].text == ":":
                locale = args[3]
            else:
                continue
            yield Interpretation(
                args[0].text,
                unquote(locale),
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


def entities(theory: Theory, name: str, path: Path, derived: bool = False) -> Iterator[Entity]:
    """Every named declaration of ``theory`` (named ``name``, read from
    ``path``); with ``derived``, also the facts the declarations derive
    (``f_def``, ``f.simps``, the rules of an inductive, ...)."""
    stops = {b.statement: b.stop for b in theory.goal_blocks()}
    scopes: list[str] = []  # "" for an anonymous block
    commands = theory.commands
    for i, command in enumerate(commands):
        toks = list(significant(command.tokens(theory.tokens)))
        while toks and toks[0].text != command.name:  # `private`, `qualified`
            toks.pop(0)
        args = toks[1:]
        if command.kind is CommandKind.THY_END and command.name == "end":
            if scopes:
                scopes.pop()
            continue
        if command.name in KINDS:
            target, j = _target(args)
            scope = target or next((s for s in reversed(scopes) if s), "")
            last = commands[stops.get(i, i + 1) - 1]
            start = theory.start(command)
            start = theory.text.rfind("\n", 0, start) + 1
            end = theory.end(last)
            for bound in _names(command.name, args[j:]):
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
                )
                yield entity
                # Parameters (`fixes`) are constants of the locale, and named
                # assumptions its facts; a class's are named in its `_class`
                # locale: `c_class.op`.
                if command.name in ("locale", "class"):
                    declaration = parse_declaration(theory, command, path)
                    local = bound if command.name == "locale" else f"{bound}_class"
                    for parameter in declaration.fixes if declaration else []:
                        yield replace(
                            entity,
                            name=parameter.name,
                            kind="constant",
                            command="fixes",
                            scope=local,
                            doc="",
                        )
                    # Named assumptions are facts of the locale.
                    for assumption in declaration.assumes if declaration else []:
                        if assumption.name:
                            yield replace(
                                entity,
                                name=assumption.name,
                                kind="fact",
                                command="assumes",
                                scope=local,
                                doc="",
                            )
                # Record fields are constants named in the record: `r.field`.
                if command.name == "record":
                    for field_name in _record_fields(args[j:]):
                        yield replace(
                            entity,
                            name=field_name,
                            kind="constant",
                            command="record",
                            scope=bound,
                            doc="",
                        )
                if derived:
                    for fact in _derived(command.name, bound, args[j:]):
                        yield replace(
                            entity, name=fact, kind="fact", doc="", derived_from=entity.qualified
                        )
        if command.kind is CommandKind.THY_DECL_BLOCK and args and args[-1].text == "begin":
            # `context fixes ... begin` is anonymous; `context loc begin` is not.
            named = command.name in _SCOPES and (command.name != "context" or len(args) == 2)
            scopes.append(unquote(args[0]) if named and len(args) >= 2 else "")


def source(theory: Theory, entity: Entity) -> str:
    """The entity's source text, dedented, with ``\\n`` line breaks and one
    final newline, so it does not depend on the line endings of a checkout."""
    text = theory.text[entity.start : entity.end].replace("\r\n", "\n").replace("\r", "\n")
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
