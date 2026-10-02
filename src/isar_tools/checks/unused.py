"""``unused`` group: declarations nothing in the project uses.

``unused-lemma``: a named fact (``lemma``, ``theorem``, ``lemmas``, ...) that
no other text of the project cites. Citing is read lexically: the name, alone
or qualified (``T.foo``, ``q.foo`` of an interpretation, ``foo(2)``,
``foo[OF ...]``), anywhere in formal text outside the fact's own statement and
proof, or in an antiquotation of document text (``@{thm foo}``,
``\\<^fact>\\<open>foo\\<close>``). A fact declared with an attribute that
registers it (``[simp]``, ``[intro]``, a ``named_theorems`` collection, ...)
is used without being named and is never reported. The same name used for
anything else counts as a citation, so the check misses rather than invents.

A project's main results are often cited only outside it, in a paper or a
manifest: ``--allow NAME`` (or ``check.allow``) or an ``isar-ignore`` comment
keeps one.
"""

import re
from bisect import bisect_left
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.project.hierarchy import bracket_group
from isar_tools.project.model import Project
from isar_tools.project.names import Entity, entities
from isar_tools.project.workspace import SourceFile
from isar_tools.source.files import read_source
from isar_tools.source.keywords import DOCUMENT
from isar_tools.source.lexer import IDENTIFIER_RE, Kind, Token
from isar_tools.source.theory import Theory, parse_theory, significant, unquote

_NAME = re.compile(rf"{IDENTIFIER_RE.pattern}(?:\.{IDENTIFIER_RE.pattern})*")
_TEXT_KINDS = frozenset({Kind.WORD, Kind.STRING, Kind.CARTOUCHE, Kind.VERBATIM, Kind.ALT_STRING})
# Attributes that transform a fact or describe its cases without registering it
# anywhere; any other attribute puts the fact to use without its name.
_INERT_ATTRIBUTES = frozenset(
    {
        "case_names",
        "case_conclusion",
        "consumes",
        "params",
        "rule_format",
        "unfolded",
        "folded",
        "simplified",
        "symmetric",
        "OF",
        "of",
        "where",
        "THEN",
        "elim_format",
        "abs_def",
        "no_vars",
        "format",
        "rotated",
        "zero_var_indexes",
    }
)
_OPEN = ("\\<open>", "‹")
_CLOSE = ("\\<close>", "›")
_CONTROL_CARTOUCHE = re.compile(r"\\<\^[A-Za-z_]+>\s*(?=\\<open>|‹)")


def _starts(text: str, i: int, markers: tuple[str, ...]) -> str:
    return next((m for m in markers if text.startswith(m, i)), "")


def _cartouche_end(text: str, i: int) -> int:
    """The index after the cartouche opened at ``i``."""
    depth = 0
    while i < len(text):
        if marker := _starts(text, i, _OPEN):
            depth += 1
            i += len(marker)
        elif marker := _starts(text, i, _CLOSE):
            depth -= 1
            i += len(marker)
            if depth == 0:
                return i
        else:
            i += 1
    return i


def _braces_end(text: str, i: int) -> int:
    """The index after the ``{...}`` opened at ``i``."""
    depth = 0
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return j + 1
    return len(text)


def antiquotations(text: str) -> Iterator[tuple[int, int]]:
    """Spans of the antiquotations in document text: ``@{...}`` and
    ``\\<^name>\\<open>...\\<close>``."""
    i = 0
    while i < len(text):
        if text.startswith("@{", i):
            end = _braces_end(text, i + 1)
        elif m := _CONTROL_CARTOUCHE.match(text, i):
            end = _cartouche_end(text, m.end())
        else:
            i += 1
            continue
        yield i, end
        i = end


def uses(theory: Theory) -> Iterator[tuple[str, int]]:
    """Names that formal text and antiquotations use, each also by its parts
    (``q.foo`` uses ``q`` and ``foo``), with their offsets."""
    for command in theory.commands:
        document = command.kind in DOCUMENT
        for tok in significant(command.tokens(theory.tokens)):
            if tok.kind not in _TEXT_KINDS:
                continue
            spans = antiquotations(tok.text) if document else [(0, len(tok.text))]
            for start, end in spans:
                for m in _NAME.finditer(tok.text, start, end):
                    offset = tok.start + m.start()
                    yield m.group(0), offset
                    for part in m.group(0).split(".")[1:]:
                        yield part, offset


def _name_token(toks: list[Token], starts: list[int], entity: Entity) -> int:
    """Index of the token naming ``entity`` in ``toks``, whose offsets are
    ``starts``; -1 if none."""
    span = range(bisect_left(starts, entity.start), bisect_left(starts, entity.end))
    return next((i for i in span if unquote(toks[i]) == entity.name), -1)


def _registers(toks: list[Token], index: int) -> bool:
    """Whether the fact named at ``toks[index]`` carries an attribute that
    puts it to use: ``foo [simp]:``."""
    rest = toks[index + 1 :]
    if [t.text for t in rest[:1]] != ["["]:
        return False
    group, _ = bracket_group(rest, 0)
    names = [group[i + 1].text for i, t in enumerate(group[:-1]) if t.text in ("[", ",")]
    return any(name not in _INERT_ATTRIBUTES for name in names)


@dataclass
class _Read:
    path: Path
    theory: Theory
    facts: list[Entity]


def _facts(theory: Theory, name: str, path: Path) -> list[Entity]:
    return [
        e
        for e in entities(theory, name, path)
        if e.kind == "fact" and not e.member and e.command != "named_theorems"
    ]


def check_unused(sources: Iterable[SourceFile], *, allow: Iterable[str] = ()) -> list[Finding]:
    """``unused-lemma`` findings for the facts ``sources`` declare. Citations
    are looked for in every theory of each source's project."""
    allowed = frozenset(allow)
    by_project: dict[int, tuple[Project, list[Path]]] = {}
    for source in sources:
        by_project.setdefault(id(source.project), (source.project, []))[1].append(source.path)
    findings: list[Finding] = []
    for project, paths in by_project.values():
        universe = [
            p
            for p in dict.fromkeys(project.closure([*paths, *project.theory_files()], None))
            if (session := project.session_of(p)) is None or not session.external
        ]
        cited: dict[str, list[tuple[Path, int]]] = {}
        read: list[_Read] = []
        checked = set(paths)
        for path in universe:
            theory = parse_theory(read_source(path), project.keywords_for(path))
            for name, offset in uses(theory):
                cited.setdefault(name, []).append((path, offset))
            if path in checked:
                name = theory.header.name.text if theory.header else path.stem
                read.append(_Read(path, theory, _facts(theory, name, path)))
        for r in read:
            findings += _unused_facts(r, cited, allowed)
    return findings


def _unused_facts(
    r: _Read, cited: dict[str, list[tuple[Path, int]]], allowed: frozenset[str]
) -> Iterator[Finding]:
    toks = list(significant(r.theory.tokens))
    starts = [t.start for t in toks]
    for fact in r.facts:
        if fact.name in allowed or fact.qualified in allowed:
            continue
        index = _name_token(toks, starts, fact)
        if index < 0 or _registers(toks, index):
            continue
        if any(
            path != r.path or not fact.start <= offset < fact.end
            for path, offset in cited.get(fact.name, ())
        ):
            continue
        yield Finding.at(
            r.path,
            r.theory.lines,
            toks[index].start,
            "unused-lemma",
            f"{fact.command} {fact.name} is cited nowhere in the project",
        )
