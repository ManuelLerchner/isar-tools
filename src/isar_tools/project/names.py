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
from dataclasses import dataclass
from pathlib import Path

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


def entities(theory: Theory, name: str, path: Path) -> Iterator[Entity]:
    """Every named declaration of ``theory`` (named ``name``, read from ``path``)."""
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
                yield Entity(
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
        if command.kind is CommandKind.THY_DECL_BLOCK and args and args[-1].text == "begin":
            # `context fixes ... begin` is anonymous; `context loc begin` is not.
            named = command.name in _SCOPES and (command.name != "context" or len(args) == 2)
            scopes.append(unquote(args[0]) if named and len(args) >= 2 else "")


def source(theory: Theory, entity: Entity) -> str:
    """The entity's source text, dedented, with one final newline."""
    return textwrap.dedent(theory.text[entity.start : entity.end]).rstrip() + "\n"


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
