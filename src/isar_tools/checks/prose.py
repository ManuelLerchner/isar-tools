"""``prose`` group: names cited in document text, and text LaTeX cannot take.

Isabelle checks antiquotations such as ``\\<^const>\\<open>f\\<close>`` against
the theory, so a rename breaks the build. A plain nested cartouche,
``text \\<open>... \\<open>f_def\\<close> ...\\<close>``, is not checked, yet it is
how prose usually cites a lemma: no short antiquotation names a fact without
printing its statement. So such a reference is reported when no declaration
of the project or of a ``-d`` directory has that name
(``prose-reference``). Only identifiers that look like names are read: at
least four characters with an underscore, as for ``locales``; ``--allow``
accepts one.

The names are those ``isar project names --derived`` lists, so ``f_def``,
``f.simps``, and interpretation facts resolve; ``x.y`` resolves when a
declaration answers to it as a qualified name.

``prose-underscore``: a raw ``_`` in the outer prose of a document command
reaches LaTeX unescaped and fails the document build ("Missing $ inserted").
Underscores inside nested cartouches, antiquotations, and symbols such as
``\\<^sub>`` are rendered by Isabelle and are fine.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.checks.locales import reportable
from isar_tools.project.model import Project
from isar_tools.project.names import (
    Entity,
    Interpretation,
    entities,
    interpretations,
    interpreted,
)
from isar_tools.project.workspace import SourceFile
from isar_tools.source.files import read_lenient
from isar_tools.source.keywords import CommandKind
from isar_tools.source.lexer import Kind
from isar_tools.source.theory import Theory, parse_theory, significant

_DOCUMENT = frozenset({CommandKind.DOCUMENT_HEADING, CommandKind.DOCUMENT_BODY})
_OPEN = ("\\<open>", "‹")
_CLOSE = ("\\<close>", "›")
_SYMBOL = re.compile(r"\\<[^>\n]*>")
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_']*(?:\.[A-Za-z][A-Za-z0-9_']*)*")


@dataclass(frozen=True)
class _Reference:
    name: str
    offset: int  # of the name, in the theory text


def _starts(text: str, i: int, markers: tuple[str, ...]) -> str:
    return next((m for m in markers if text.startswith(m, i)), "")


def _skip_antiquotation(text: str, i: int) -> int:
    """The index after the ``@{...}`` starting at ``i``; braces and cartouches
    nest."""
    depth = 0
    cartouches = 0
    i += 1  # the `{`
    while i < len(text):
        if marker := _starts(text, i, _OPEN):
            cartouches += 1
            i += len(marker)
            continue
        if marker := _starts(text, i, _CLOSE):
            cartouches -= 1
            i += len(marker)
            continue
        if not cartouches:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
        if not depth and not cartouches:
            break
    return i


def scan(text: str, start: int) -> tuple[list[_Reference], list[int]]:
    """Plain references and raw underscores in the cartouche ``text`` found at
    offset ``start``: the nested cartouches that are no antiquotation's
    argument and hold just a name, and the ``_`` of the outer prose."""
    references: list[_Reference] = []
    underscores: list[int] = []
    depth = 0
    i = 0
    after_control = False  # the next cartouche is an antiquotation's argument
    opened = 0  # where the content of the current plain cartouche starts
    plain = False
    while i < len(text):
        if marker := _starts(text, i, _OPEN):
            depth += 1
            i += len(marker)
            if depth == 2:
                plain, opened = not after_control, i
            after_control = False
            continue
        if marker := _starts(text, i, _CLOSE):
            if depth == 2 and plain and _NAME.fullmatch(text[opened:i]):
                references.append(_Reference(text[opened:i], start + opened))
            depth -= 1
            i += len(marker)
            continue
        if symbol := _SYMBOL.match(text, i):
            after_control = symbol.group(0).startswith("\\<^") or symbol.group(0) == "\\<comment>"
            i = symbol.end()
            continue
        after_control = False
        if depth == 1 and text.startswith("@{", i):
            i = _skip_antiquotation(text, i)
            continue
        if depth == 1 and text[i] == "_":
            underscores.append(start + i)
        i += 1
    return references, underscores


def _document_text(theory: Theory) -> Iterator[tuple[str, int]]:
    """The cartouche argument of each document command, with its offset."""
    for command in theory.commands:
        if command.kind not in _DOCUMENT:
            continue
        for tok in significant(command.tokens(theory.tokens)):
            if tok.kind is Kind.CARTOUCHE:
                yield tok.text, tok.start
                break


def _spellings(entity: Entity) -> Iterator[str]:
    yield entity.name
    yield entity.qualified
    yield f"{entity.theory}.{entity.name}"
    if entity.scope:
        yield f"{entity.scope}.{entity.name}"


def _formal_names(theory: Theory) -> Iterator[str]:
    """Names used outside document text and comments: in terms, proofs, ML,
    and as the arguments of commands."""
    for command in theory.commands:
        if command.kind in _DOCUMENT or command.kind is CommandKind.DOCUMENT_RAW:
            continue
        for tok in significant(command.tokens(theory.tokens)):
            if tok.kind in (Kind.WORD, Kind.STRING, Kind.CARTOUCHE, Kind.VERBATIM):
                for name in _NAME.findall(tok.text):
                    yield name
                    yield from name.split(".")


def known_names(project: Project) -> set[str]:
    """What a prose reference may name: every spelling of every declaration
    of the project and its ``-d`` directories (derived facts included), their
    theories and sessions, and every name their formal text uses, such as a
    constant of HOL, a proof method, or a local variable."""
    found: list[Entity] = []
    interps: list[Interpretation] = []
    names: set[str] = set()
    for session in project.sessions.values():
        names.add(session.name)
        for name, path in project.owned_theories(session).items():
            theory = parse_theory(read_lenient(path), project.keywords_for(path))
            found += entities(theory, name, path, derived=True)
            interps += interpretations(theory, name, path)
            names |= {name, f"{session.name}.{name}", *_formal_names(theory)}
            header = theory.header
            names |= {i.text.rpartition(".")[2] for i in header.imports} if header else set()
    found += [e for i in interps for e in interpreted(found, i)]
    return names | {s for e in found for s in _spellings(e)}


def check_prose(
    sources: Iterable[SourceFile], theories: dict[Path, Theory], *, allow: Iterable[str] = ()
) -> list[Finding]:
    """``prose-reference`` and ``prose-underscore`` findings of ``sources``,
    parsed as ``theories``."""
    allowed = frozenset(allow)
    known: dict[int, set[str]] = {}
    findings: list[Finding] = []
    for source in sources:
        theory = theories[source.path]
        for text, start in _document_text(theory):
            references, underscores = scan(text, start)
            findings += [
                Finding.at(
                    source.path,
                    theory.lines,
                    offset,
                    "prose-underscore",
                    "raw _ in document prose reaches LaTeX unescaped; cite the name in a "
                    "cartouche or an antiquotation",
                )
                for offset in underscores
            ]
            for ref in references:
                if ref.name in allowed or not reportable(ref.name):
                    continue
                key = id(source.project)
                if key not in known:
                    known[key] = known_names(source.project)
                # `q.fact` of an interpretation may be a fact its locale
                # inherits, which is not listed: its base name has to do.
                if ref.name not in known[key] and ref.name.rpartition(".")[2] not in known[key]:
                    findings.append(
                        Finding.at(
                            source.path,
                            theory.lines,
                            ref.offset,
                            "prose-reference",
                            f"{ref.name} names no declaration of the project",
                        )
                    )
    return findings
