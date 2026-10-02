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
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.project.hierarchy import bracket_group
from isar_tools.project.model import Project
from isar_tools.project.names import Entity, entities
from isar_tools.project.workspace import SourceFile
from isar_tools.source.files import read_lenient
from isar_tools.source.keywords import DOCUMENT, CommandKind
from isar_tools.source.lexer import IDENTIFIER_RE, Kind, Token
from isar_tools.source.theory import Command, Theory, parse_theory, significant, unquote

_NAME = re.compile(rf"{IDENTIFIER_RE.pattern}(?:\.{IDENTIFIER_RE.pattern})*")
_TEXT_KINDS = frozenset({Kind.WORD, Kind.STRING, Kind.CARTOUCHE, Kind.VERBATIM, Kind.ALT_STRING})
# Attributes that transform a fact or describe its cases without registering it
# anywhere; any other attribute puts the fact to use without its name.
INERT_ATTRIBUTES = frozenset(
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
        if command.kind is CommandKind.THY_BEGIN:
            continue  # the header names theories, not what they declare
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
    return any(name not in INERT_ATTRIBUTES for name in attribute_names(group))


def _facts(theory: Theory, name: str, path: Path) -> list[Entity]:
    return [
        e
        for e in entities(theory, name, path)
        if e.kind == "fact" and not e.member and e.command != "named_theorems"
    ]


def _theory_name(theory: Theory, path: Path) -> str:
    return theory.header.name.text if theory.header else path.stem


class _Index:
    """The theories of a project, read once, and what each uses and adds."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self._theories: dict[Path, Theory] = {}
        self._reach: dict[Path, frozenset[Path]] = {}
        self._provided: dict[Path, frozenset[str]] = {}
        self._implicit: dict[Path, bool] = {}
        self._own: list[Path] = []
        self._dependents: dict[Path, set[Path]] = {}
        self._used: dict[Path, frozenset[str]] = {}

    def theory(self, path: Path) -> Theory:
        if path not in self._theories:
            text = read_lenient(path)
            self._theories[path] = parse_theory(text, self.project.keywords_for(path))
        return self._theories[path]

    def own(self, paths: Iterable[Path]) -> list[Path]:
        """``paths``, the project's theories, and what they import, without
        included (``-d``) theories."""
        start = [*paths, *self.project.theory_files()]
        self._own = [
            p
            for p in dict.fromkeys(self.project.closure(start, None))
            if (session := self.project.session_of(p)) is None or not session.external
        ]
        return self._own

    def reach(self, path: Path) -> frozenset[Path]:
        """``path`` and every project theory it imports, transitively."""
        if path not in self._reach:
            session = self.project.session_of(path)
            self._reach[path] = frozenset(self.project.closure([path], session))
        return self._reach[path]

    def provided(self, path: Path) -> frozenset[str]:
        """Every spelling of every name the theory declares, derived facts
        included, and the theory's own name."""
        if path not in self._provided:
            theory = self.theory(path)
            name = _theory_name(theory, path)
            names = {name}
            for e in entities(theory, name, path, derived=True):
                names |= {e.name, e.qualified, f"{name}.{e.name}"}
                if e.scope:
                    names.add(f"{e.scope}.{e.name}")
            self._provided[path] = frozenset(names)
        return self._provided[path]

    def used_downstream(self, path: Path) -> frozenset[str]:
        """Names the theory uses, and every theory of the project that imports
        it, directly or not: an import also serves the importers."""
        if not self._dependents:
            for theory in self._own:
                for reached in self.reach(theory):
                    self._dependents.setdefault(reached, set()).add(theory)
        users = self._dependents.get(path, set()) | {path}
        return frozenset(name for user in users for name in self.used(user))

    def used(self, path: Path) -> frozenset[str]:
        """Names the theory uses."""
        if path not in self._used:
            self._used[path] = frozenset(name for name, _ in uses(self.theory(path)))
        return self._used[path]

    def implicit(self, path: Path) -> bool:
        """Whether the theory can be needed without any of its names: it
        declares commands, instances, simp rules, notation, or ML."""
        if path not in self._implicit:
            theory = self.theory(path)
            keywords = theory.header is not None and bool(theory.header.keywords)
            commands = any(_implicit(theory, command) for command in theory.commands)
            # A constant with a mixfix is used through its notation, not its name.
            mixfix = any(e.mixfix for e in entities(theory, _theory_name(theory, path), path))
            self._implicit[path] = keywords or commands or mixfix
        return self._implicit[path]


def check_unused(sources: Iterable[SourceFile], *, allow: Iterable[str] = ()) -> list[Finding]:
    """``unused-lemma`` and ``unused-import`` findings for ``sources``.
    Citations are looked for in every theory of each source's project."""
    allowed = frozenset(allow)
    by_project: dict[int, tuple[Project, list[Path]]] = {}
    for source in sources:
        by_project.setdefault(id(source.project), (source.project, []))[1].append(source.path)
    findings: list[Finding] = []
    for project, paths in by_project.values():
        index = _Index(project)
        cited: dict[str, list[tuple[Path, int]]] = {}
        for path in index.own(paths):
            for name, offset in uses(index.theory(path)):
                cited.setdefault(name, []).append((path, offset))
        for path in paths:
            theory = index.theory(path)
            findings += _unused_facts(path, theory, cited, allowed)
            findings += _unused_assumptions(path, theory, cited, allowed)
            findings += _unused_imports(path, theory, index)
    return findings


def _cited_elsewhere(
    cited: dict[str, list[tuple[Path, int]]], name: str, path: Path, entity: Entity
) -> bool:
    """Whether ``name`` is used outside the extent of ``entity``."""
    return any(
        where != path or not entity.start <= offset < entity.end
        for where, offset in cited.get(name, ())
    )


def _unused_facts(
    path: Path, theory: Theory, cited: dict[str, list[tuple[Path, int]]], allowed: frozenset[str]
) -> Iterator[Finding]:
    toks = list(significant(theory.tokens))
    starts = [t.start for t in toks]
    for fact in _facts(theory, _theory_name(theory, path), path):
        if fact.name in allowed or fact.qualified in allowed:
            continue
        index = _name_token(toks, starts, fact)
        if index < 0 or _registers(toks, index):
            continue
        if _cited_elsewhere(cited, fact.name, path, fact):
            continue
        yield Finding.at(
            path,
            theory.lines,
            toks[index].start,
            "unused-lemma",
            f"{fact.command} {fact.name} is cited nowhere in the project",
        )


# Commands whose effect a theory importing them can rely on without naming
# anything they declare.
_IMPLICIT_COMMANDS = frozenset(
    {
        "instantiation",
        "instance",
        "interpretation",
        "global_interpretation",
        "sublocale",
        "declare",
        "setup",
        "local_setup",
        "method_setup",
        "attribute_setup",
        "simproc_setup",
        "declaration",
        "syntax_declaration",
        "notation",
        "no_notation",
        "type_notation",
        "no_type_notation",
        "syntax",
        "no_syntax",
        "translations",
        "no_translations",
        "parse_translation",
        "print_translation",
        "adhoc_overloading",
        "no_adhoc_overloading",
        "open_bundle",
        "unbundle",
        "code_printing",
        "code_datatype",
        "hide_const",
        "hide_fact",
        "hide_type",
        "hide_class",
        "default_sort",
        "setup_lifting",
        "lifting_update",
        "lifting_forget",
    }
)
_FACT_COMMANDS = frozenset({"lemma", "theorem", "corollary", "proposition", "lemmas", "theorems"})


def attribute_names(group: list[Token]) -> list[str]:
    """The attribute names of ``[a x, b]``: ``a`` and ``b``."""
    return [group[i + 1].text for i, t in enumerate(group[:-1]) if t.text in ("[", ",")]


def _implicit(theory: Theory, command: Command) -> bool:
    """Whether ``command`` has an effect beyond the names it declares: an
    instance, ML, notation, or a fact with a registering attribute."""
    if command.name in _IMPLICIT_COMMANDS or "ML" in command.name:
        return True
    if command.name not in _FACT_COMMANDS:
        return False
    toks = list(significant(command.tokens(theory.tokens)))
    # `lemma [simp]: ...` or `lemma foo [intro]: ...`
    at = 1 if len(toks) > 1 and toks[1].text == "[" else 2
    if len(toks) <= at or toks[at].text != "[":
        return False
    group, _ = bracket_group(toks, at)
    return any(name not in INERT_ATTRIBUTES for name in attribute_names(group))


def _unused_imports(path: Path, theory: Theory, index: _Index) -> Iterator[Finding]:
    """``redundant-import``: an import another import reaches already;
    ``unused-import``: an import of which nothing it adds is used, by the
    theory or by any theory that imports it, once the redundant imports are
    gone."""
    header = theory.header
    if header is None:
        return
    session = index.project.session_of(path)
    imports = [
        (imp, target)
        for imp in header.imports
        if (target := index.project.resolve_import(path, session, imp.text)) is not None
    ]
    redundant: set[Path] = set()
    for imp, target in imports:
        others = [(i, t) for i, t in imports if t != target]
        via = next((i for i, t in others if target in index.reach(t)), None)
        if via is not None:
            redundant.add(target)
            message = f"{imp.text} is imported through {via.text} already"
            yield Finding.at(path, theory.lines, imp.start, "redundant-import", message)
    # Removing every redundant import keeps the same theories reachable, and
    # only then does an import alone bring in what it adds.
    kept = [(imp, target) for imp, target in imports if target not in redundant]
    used = index.used_downstream(path)
    for imp, target in kept:
        others = (index.reach(t) for _, t in kept if t != target)
        exclusive = index.reach(target).difference(*others)
        if any(index.implicit(p) for p in exclusive):
            continue
        if not any(index.provided(p) & used for p in exclusive):
            message = f"imports {imp.text}, but nothing uses what it adds"
            yield Finding.at(path, theory.lines, imp.start, "unused-import", message)


# Facts of a locale that hold all its assumptions at once.
_WHOLE = ("{}_axioms", "{}_def", "{}.axioms", "{}_axioms_def")


def _unused_assumptions(
    path: Path, theory: Theory, cited: dict[str, list[tuple[Path, int]]], allowed: frozenset[str]
) -> Iterator[Finding]:
    """``unused-assumption``: a named assumption of a locale or class that no
    proof cites, while nothing cites the locale's assumptions as a whole."""
    toks = list(significant(theory.tokens))
    starts = [t.start for t in toks]
    for e in entities(theory, _theory_name(theory, path), path):
        if not (e.member and e.command == "assumes") or e.name in allowed:
            continue
        locale = e.scope
        if any(_cited_elsewhere(cited, whole.format(locale), path, e) for whole in _WHOLE):
            continue
        index = _name_token(toks, starts, e)
        if index < 0 or _registers(toks, index) or _cited_elsewhere(cited, e.name, path, e):
            continue
        kind = "class" if locale.endswith("_class") else "locale"
        message = (
            f"assumption {e.name} of {kind} {locale.removesuffix('_class')} is cited nowhere; "
            f"the {kind} may assume less"
        )
        start = toks[index].start
        yield Finding.at(path, theory.lines, start, "unused-assumption", message)
