"""``notation`` group: a constant written out where it has a short form.

A project gives a constant a short form in four ways, and once it has, every
later term should use it:

- a mixfix on its declaration (``definition``, ``fun``, ``consts``, a class or
  locale parameter, a record field, ...): ``f x`` should be written in that
  mixfix;
- a ``notation f (mixfix)`` command, likewise (``notation (input)`` counts,
  other print modes do not);
- ``adhoc_overloading g == f``: ``f x`` should be written ``g x``. An
  instance that is a term (``"lift f"``) is matched as that token sequence.
  Not where no type resolves ``g``: in an attribute instantiation
  (``[where x = "f"]``, ``[of "f"]``) or as a bracketed argument
  (``map (f x)``);
- any of these inside ``bundle B begin ... end``: the short form holds where
  ``B`` is open, by ``unbundle B`` (until ``unbundle no B``), ``open_bundle``,
  ``includes B``, ``including B``, or a bundle that unbundles ``B``.

``spelled-out-abbreviation``: a term that is the right-hand side of an
``abbreviation``, its variables matching any argument, should be written as
the abbreviation. Not followed: an alias of one token, a right-hand side that
starts with a variable, and ``c x \\<equiv> f x``, which only narrows the type
of ``f``. A right-hand side with an operator outside brackets matches only a
whole term (bracketed, between separators, or the whole string), since
precedence may split it otherwise. An abbreviation declared in an anonymous
block holds only there, and one from an included session (``-d``) not at all:
it may fix types the project's terms do not have.

A short form holds after the command that introduces it, in its theory and in
every theory importing it. Inside a ``locale``, ``class``, or ``context NAME``
block (or after ``(in NAME)``) it holds in that locale and the locales
extending it; inside an anonymous block, only there. A locale's or class's own
parameters hold already in its header; any other declaration may spell itself
out in its own defining equations.

Terms are read lexically, as for ``locales``: the strings and cartouches of
formal commands, without document text, comments, ML, syntax commands, mixfix
annotations, and types after ``::``. Names bound in the term, or fixed by
``fixes``, ``for``, ``fix``, ``obtain``, ``define``, or ``case (C x)`` in the
command, its goal, or its block, are variables. A mixfix needs its arguments,
so a name is reported only when an argument follows it; an infix also has the
unapplied form ``(op)`` and is always reported. Qualified names
(``T.f``) and ``no_notation`` are not followed.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.checks.locales import bound_names, term_text
from isar_tools.checks.terms import (
    TEXTS,
    argument_end,
    arguments,
    delimited,
    has_operator,
    heads,
    match,
    spelling,
    term_tokens,
)
from isar_tools.project.hierarchy import bracket_group, declarations, parse_mixfix
from isar_tools.project.model import Project
from isar_tools.project.names import Entity, entities
from isar_tools.project.names import source as statement_source
from isar_tools.project.notation import INFIX, NotationError, expansion, template
from isar_tools.project.workspace import SourceFile
from isar_tools.source.files import read_lenient
from isar_tools.source.keywords import DOCUMENT, CommandKind
from isar_tools.source.lexer import IGNORABLE, Kind, Token, tokenize
from isar_tools.source.symbols import encode
from isar_tools.source.theory import Command, Theory, parse_theory, significant, unquote

CODE = "spelled-out-notation"
ABBREVIATION_CODE = "spelled-out-abbreviation"

# Commands whose strings and cartouches are no terms of the theory.
_NOTEXTS = frozenset(
    {
        "setup",
        "local_setup",
        "attribute_setup",
        "method_setup",
        "simproc_setup",
        "declaration",
        "syntax_declaration",
        "parse_ast_translation",
        "parse_translation",
        "print_translation",
        "typed_print_translation",
        "print_ast_translation",
        "oracle",
        "syntax",
        "no_syntax",
        "translations",
        "no_translations",
        "notation",
        "no_notation",
        "type_notation",
        "no_type_notation",
        "adhoc_overloading",
        "no_adhoc_overloading",
        "code_printing",
        "code_reserved",
        "code_identifier",
        "export_code",
    }
)
# A string after one of these is a mixfix, a type, or a target, not a term.
_NOT_TERM_AFTER = frozenset({"(", "::", "in", "binder", *INFIX})
# Elements that fix variables, and the words that end the variables.
_FIXING = frozenset({"fixes", "for", "fix", "obtain", "obtains", "define"})
_FIXED_END = frozenset(
    {"where", "assumes", "shows", "obtains", "if", "when", "begin", "defines", "notes"}
)
_INCLUDING = frozenset({"includes", "including"})


@dataclass(frozen=True)
class Scope:
    kind: str  # "global", "locale", "block", or "bundle"
    name: str = ""  # the locale or bundle; for a block, its command index


@dataclass(frozen=True)
class ShortForm:
    pattern: tuple[str, ...]  # the written-out term, as tokens with ASCII symbols
    advice: str  # what to write instead
    # Arguments a use needs before the short form can replace it; 0 for one
    # that also has an unapplied form: an infix `(op)`, a notation without
    # slots.
    arity: int
    scope: Scope
    path: Path
    after: int  # index of the command that introduces it
    home: bool = False  # holds inside that command too: a locale's own parameters
    variables: frozenset[str] = frozenset()  # pattern items that match any argument
    code: str = CODE
    # The pattern has an operator outside brackets: a match must be a whole
    # term, or precedence may split it (`a \<and> b` in `a \<and> b \<and> c`).
    whole: bool = False
    # An adhoc_overloading instance: Isabelle resolves the generic name by type.
    overloaded: bool = False

    @property
    def applied(self) -> bool:
        """Whether a use has to head an application: a mixfix with slots, or
        a pattern that is an application itself."""
        return self.arity > 0 or len(self.pattern) > 1


@dataclass(frozen=True)
class _Context:
    """What holds at a command."""

    locale: str  # its target or innermost named block; "" if none
    blocks: frozenset[int]  # the command indices of the blocks around it
    bundles: frozenset[str]  # open bundles, before following unbundle chains
    variables: frozenset[str]
    terms: bool  # its strings and cartouches are terms that are checked


_NO_CONTEXT = _Context("", frozenset(), frozenset(), frozenset(), False)


@dataclass
class _Block:
    index: int
    locale: str = ""
    bundle: str = ""  # the bundle whose body this is
    opened: set[str] = field(default_factory=set[str])
    variables: frozenset[str] = frozenset()


@dataclass
class _Analysis:
    theory: Theory
    contexts: list[_Context]
    opened: frozenset[str]  # bundles open at the end, at theory level
    forms: list[ShortForm]
    includes: dict[str, set[str]]  # bundle -> the bundles it unbundles


def _tokens(theory: Theory, command: Command) -> list[Token]:
    """The tokens of ``command`` from its keyword, after ``private``."""
    toks = list(significant(command.tokens(theory.tokens)))
    while toks and toks[0].text != command.name:
        toks.pop(0)
    return toks


def _words_after(args: list[Token], keywords: frozenset[str]) -> Iterator[str]:
    """The names following any of ``keywords``: ``unbundle a b``."""
    for i, tok in enumerate(args):
        if tok.text in keywords:
            for name in args[i + 1 :]:
                if name.kind is not Kind.WORD or name.text in _FIXED_END | keywords:
                    break
                yield name.text


def _bundle_changes(args: list[Token]) -> tuple[set[str], set[str]]:
    """Bundles ``unbundle a no b`` opens and closes."""
    opened: set[str] = set()
    closed: set[str] = set()
    target = opened
    for tok in (t for t in args if t.kind is Kind.WORD):
        if tok.text == "no":
            target = closed
        else:
            target.add(tok.text)
    return opened, closed


def _variables(toks: list[Token]) -> set[str]:
    """Variables the command ``toks`` fixes: ``fix x :: T and y``, ``for x``,
    ``case (C x y)``; not a parameter with a mixfix, which is a short form."""
    names: set[str] = set()
    for i, tok in enumerate(toks):
        if tok.text == "case" and i + 2 < len(toks) and toks[i + 1].text == "(":
            group, _ = bracket_group(toks, i + 1)
            names.update(t.text for t in group[2:] if t.kind is Kind.WORD)
        if tok.text not in _FIXING:
            continue
        entry: list[str] = []
        j = i + 1
        while j < len(toks):
            t = toks[j]
            if t.text == "::":
                j += 2
            elif t.text == "(" and entry:  # a mixfix ends the entry
                entry = []
                j = bracket_group(toks, j)[1]
            elif t.kind is not Kind.WORD or t.text in _FIXED_END | _FIXING:
                break
            else:
                if t.text == "and":
                    names.update(entry)
                    entry = []
                else:
                    entry.append(t.text)
                j += 1
        names.update(entry)
    return names


def _target(args: list[Token]) -> str:
    if len(args) >= 4 and args[0].text == "(" and args[1].text == "in" and args[3].text == ")":
        return unquote(args[2])
    return ""


def _scope(stack: list[_Block]) -> Scope:
    if not stack:
        return Scope("global")
    inner = stack[-1]
    if inner.bundle:
        return Scope("bundle", inner.bundle)
    if inner.locale:
        return Scope("locale", inner.locale)
    return Scope("block", str(inner.index))


def _split_and(args: list[Token]) -> list[list[Token]]:
    parts: list[list[Token]] = [[]]
    depth = 0
    for tok in args:
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(tok.text, 0)
        if depth == 0 and tok.kind is Kind.WORD and tok.text == "and":
            parts.append([])
        else:
            parts[-1].append(tok)
    return [p for p in parts if p]


def _pattern(text: str) -> tuple[str, ...]:
    return tuple(encode(t.text) for t in tokenize(text) if t.kind not in IGNORABLE)


def _shown(mixfix: str, notation: str) -> tuple[str, int] | None:
    """The notation a mixfix writes and its arity; None if it has no notation
    to suggest."""
    try:
        written = template(mixfix, notation)
    except NotationError:
        return None
    infix = mixfix.partition(" ")[0] in INFIX
    # `'_` quotes the underscore: it is no slot.
    arity = 0 if infix else len(re.findall(r"(?<!')_", written))
    return (written, arity) if written else None


def _in_bundle(scope: Scope) -> str:
    return f" (bundle {scope.name})" if scope.kind == "bundle" else ""


def _notations(args: list[Token], scope: Scope, path: Path, index: int) -> Iterator[ShortForm]:
    """``notation (input) f (mixfix) and g (mixfix)``."""
    if len(args) > 2 and args[0].text == "(" and args[2].text == ")":
        if args[1].text != "input":
            return  # a print mode: the input is still written out
        args = args[3:]
    for part in _split_and(args):
        if len(part) < 2 or part[0].kind not in (Kind.WORD, Kind.STRING) or part[1].text != "(":
            continue
        shown = _shown(*parse_mixfix(bracket_group(part, 1)[0]))
        if shown is not None:
            name = unquote(part[0]).rpartition(".")[2]
            advice = f"its notation is {shown[0]}{_in_bundle(scope)}"
            yield ShortForm((encode(name),), advice, shown[1], scope, path, index)


def _overloadings(args: list[Token], scope: Scope, path: Path, index: int) -> Iterator[ShortForm]:
    """``adhoc_overloading g == f "t u" and h == k``; the ``==`` is optional."""
    for part in _split_and(args):
        generic = unquote(part[0]).rpartition(".")[2]
        advice = f"it is overloaded as {generic}{_in_bundle(scope)}"
        instances = [t for t in part[1:] if t.kind in (Kind.WORD, Kind.STRING, Kind.CARTOUCHE)]
        for pattern in filter(None, (_pattern(unquote(t)) for t in instances)):
            yield ShortForm(pattern, advice, 1, scope, path, index, overloaded=True)


def _entity_scope(e: Entity) -> Scope:
    parameter = e.member and e.command in ("fixes", "for")
    if parameter and e.scope.endswith("_class"):
        return Scope("global")  # a class parameter is a global constant
    if e.scope and (parameter or not e.member):
        return Scope("locale", e.scope)
    return Scope("global")


def _abbreviation(theory: Theory, e: Entity, index: int, scope: Scope) -> ShortForm | None:
    r"""``abbreviation c where "c x \<equiv> f x (g x)"``: the right-hand side as
    a pattern with the variables of the left. Not reported: an alias of one
    token, a pattern that starts with a variable, and ``c x \<equiv> f x``,
    which only gives ``f`` a narrower type."""
    try:
        lhs, rhs = expansion(statement_source(theory, e, statement=True))
    except NotationError:
        return None
    parameters = [t.text for t in term_tokens(lhs) if t.kind is Kind.WORD and t.text != e.name]
    variables = frozenset(parameters)
    toks = term_tokens(rhs)
    pattern = tuple(spelling(toks))
    if len(pattern) < 2 or pattern[0] in variables or list(pattern[1:]) == parameters:
        return None
    advice = f"it is the abbreviation {e.name}"
    return ShortForm(
        pattern,
        advice,
        0,
        scope,
        e.path,
        index,
        variables=variables,
        code=ABBREVIATION_CODE,
        whole=has_operator(toks),
    )


def _declared_forms(theory: Theory, path: Path, blocks: list[Scope]) -> Iterator[ShortForm]:
    """Short forms from the mixfix of a declaration, and abbreviations.
    ``blocks`` is the scope of the block around each command."""
    name = theory.header.name.text if theory.header else path.stem
    for e in entities(theory, name, path):
        if e.kind != "constant" or e.mode == "output":
            continue
        index = e.command_index
        if e.command == "abbreviation":
            # Inside an anonymous block, the abbreviation is generalized
            # over the block's parameters when it leaves it.
            block = blocks[index]
            scope = block if block.kind == "block" else _entity_scope(e)
            if form := _abbreviation(theory, e, index, scope):
                yield form
        shown = _shown(e.mixfix, e.notation)
        if shown is None:
            continue
        parameter = e.member and e.command in ("fixes", "for")
        advice = f"its notation is {shown[0]}"
        scope = _entity_scope(e)
        yield ShortForm((encode(e.name),), advice, shown[1], scope, path, index, parameter)


def _opens_block(command: Command, args: list[Token]) -> bool:
    return command.kind is CommandKind.THY_DECL_BLOCK and bool(args) and args[-1].text == "begin"


def _analyze(path: Path, theory: Theory, opened_before: frozenset[str]) -> _Analysis:
    """Contexts and short forms of ``theory``, whose imports leave the bundles
    ``opened_before`` open."""
    goal: dict[int, tuple[set[str], set[str]]] = {}
    for block in theory.goal_blocks():
        bundles: set[str] = set()
        variables: set[str] = set()
        for k in range(block.statement, block.stop):
            toks = _tokens(theory, theory.commands[k])
            bundles.update(_words_after(toks, _INCLUDING))
            variables |= _variables(toks)
        goal.update(dict.fromkeys(range(block.statement, block.stop), (bundles, variables)))
    stack: list[_Block] = []
    opened = set(opened_before)
    contexts: list[_Context] = []
    blocks: list[Scope] = []
    forms: list[ShortForm] = []
    includes: dict[str, set[str]] = {}
    for i, command in enumerate(theory.commands):
        toks = _tokens(theory, command)
        args = toks[1:]
        if command.kind is CommandKind.THY_END:
            if stack:
                stack.pop()
            contexts.append(_NO_CONTEXT)
            blocks.append(Scope("global"))
            continue
        bundle = next((b.bundle for b in reversed(stack) if b.bundle), "")
        bundles, variables = goal.get(i) or (
            set(_words_after(toks, _INCLUDING)),
            _variables(toks),
        )
        level = opened.union(*(b.opened for b in stack))
        contexts.append(
            _Context(
                _target(args) or next((b.locale for b in reversed(stack) if b.locale), ""),
                frozenset(b.index for b in stack),
                frozenset(level | bundles),
                frozenset(variables).union(*(b.variables for b in stack)),
                not bundle
                and command.kind not in DOCUMENT
                and command.name not in _NOTEXTS
                and "ML" not in command.name,
            )
        )
        scope = _scope(stack)
        blocks.append(scope)
        if command.name == "notation":
            forms += _notations(args, scope, path, i)
        elif command.name == "adhoc_overloading":
            forms += _overloadings(args, scope, path, i)
        elif command.name == "unbundle":
            added, removed = _bundle_changes(args)
            if bundle:
                includes.setdefault(bundle, set()).update(added)
            else:
                target = stack[-1].opened if stack else opened
                target |= added
                target -= removed
        elif command.name in ("bundle", "open_bundle") and len(args) > 2 and args[1].text == "=":
            names = [t.text for t in args[2:] if t.kind is Kind.WORD]
            includes.setdefault(unquote(args[0]), set()).update(names)
        if command.name == "open_bundle" and args:
            (stack[-1].opened if stack else opened).add(unquote(args[0]))
        if _opens_block(command, args):
            block = _Block(i, variables=frozenset(_variables(toks)))
            named = command.name == "context" and len(args) == 2
            if command.name in ("locale", "class") or named:
                block.locale = unquote(args[0])
            elif command.name in ("bundle", "open_bundle"):
                block.bundle = unquote(args[0])
            elif command.name == "context":
                block.opened.update(_words_after(args, _INCLUDING))
            stack.append(block)
    forms += _declared_forms(theory, path, blocks)
    return _Analysis(theory, contexts, frozenset(opened), forms, includes)


def _field_name(toks: list[Token], i: int) -> bool:
    r"""Whether ``toks[i]`` names a record field to update or construct:
    ``r\<lparr>f := x\<rparr>``, ``\<lparr>f = x, g = y\<rparr>``."""
    after = "".join(t.text for t in toks[i + 1 : i + 3])
    before = encode(toks[i - 1].text) if i else ""
    # `:=` lexes as `:` and `=`; `(|` as `(` and `|`.
    return after == ":=" or (after[:1] == "=" and before in ("\\<lparr>", "|", ","))


class _Checker:
    def __init__(self, project: Project, allow: frozenset[str]) -> None:
        self.project = project
        self.allow = allow
        self.analyses: dict[Path, _Analysis | None] = {}
        self.parents: dict[str, set[str]] = {}
        self._visible: dict[Path, set[Path]] = {}
        self._ancestors: dict[str, set[str]] = {}

    def analysis(self, path: Path) -> _Analysis | None:
        if path in self.analyses:
            return self.analyses[path]
        self.analyses[path] = None  # an import cycle stops here
        session = self.project.session_of(path)
        header = self.project.header(path)
        opened: set[str] = set()
        for imp in header.imports if header else ():
            target = self.project.resolve_import(path, session, imp.text)
            found = self.analysis(target) if target is not None else None
            if found is not None:
                opened |= found.opened
        theory = parse_theory(read_lenient(path), self.project.keywords_for(path))
        for decl in declarations(theory, path):
            extra = decl.sorts if decl.kind == "class" else []
            self.parents.setdefault(decl.name, set()).update(decl.parents, extra)
        result = self.analyses[path] = _analyze(path, theory, frozenset(opened))
        return result

    def visible(self, path: Path) -> set[Path]:
        if path not in self._visible:
            session = self.project.session_of(path)
            self._visible[path] = set(self.project.closure([path], session))
        return self._visible[path]

    def ancestors(self, locale: str) -> set[str]:
        """``locale`` and every locale or class it extends."""
        if locale not in self._ancestors:
            seen: set[str] = set()
            stack = [locale]
            while stack:
                name = stack.pop()
                if name and name not in seen:
                    seen.add(name)
                    stack += self.parents.get(name, ())
            self._ancestors[locale] = seen
        return self._ancestors[locale]


def _expand(bundles: Iterable[str], includes: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(bundles)
    while stack:
        name = stack.pop()
        if name not in seen:
            seen.add(name)
            stack += includes.get(name, ())
    return seen


def _active(
    form: ShortForm,
    path: Path,
    index: int,
    context: _Context,
    bundles: set[str],
    checker: _Checker,
) -> bool:
    if form.path == path and index <= form.after:
        return form.home and index == form.after
    if form.path != path and form.path not in checker.visible(path):
        return False
    kind, name = form.scope.kind, form.scope.name
    if kind == "locale":
        return name in checker.ancestors(context.locale)
    if kind == "block":
        return form.path == path and int(name) in context.blocks
    if kind == "bundle":
        return name in bundles
    return True


def check_notation(sources: Iterable[SourceFile], *, allow: Iterable[str] = ()) -> list[Finding]:
    """Terms in ``sources`` that write out a constant with a short form."""
    by_project: dict[int, tuple[Project, list[Path]]] = {}
    for source in sources:
        by_project.setdefault(id(source.project), (source.project, []))[1].append(source.path)
    findings: list[Finding] = []
    for project, paths in by_project.values():
        checker = _Checker(project, frozenset(allow))
        universe = list(dict.fromkeys(project.closure([*paths, *project.theory_files()], None)))
        for path in universe:
            checker.analysis(path)
        analyses = [a for a in checker.analyses.values() if a is not None]
        includes: dict[str, set[str]] = {}
        by_first: dict[str, list[ShortForm]] = {}
        for found in analyses:
            for bundle, names in found.includes.items():
                includes.setdefault(bundle, set()).update(names)
            for form in found.forms:
                session = project.session_of(form.path)
                # An included theory's abbreviation may fix types the project's own
                # terms do not have, and is no part of its vocabulary.
                foreign = session is not None and session.external
                if foreign and form.code == ABBREVIATION_CODE:
                    continue
                if " ".join(form.pattern) not in checker.allow:
                    by_first.setdefault(form.pattern[0], []).append(form)
        for path in paths:
            found = checker.analyses[path]
            assert found is not None  # set once the import cycle guard is left
            findings += _check(path, found, by_first, includes, checker)
    return findings


def _passed_partially(toks: list[Token], start: int, end: int) -> bool:
    """Whether the application at ``toks[start:end]`` and its one argument form a
    bracket group passed as an argument, as in ``map f (g x)``: its type is a
    function the context does not fix."""
    stop = argument_end(toks, end)
    return (
        start > 1
        and toks[start - 1].text == "("
        and stop < len(toks)
        and toks[stop].text == ")"
        and not heads(toks, start - 1)
    )


def _check(
    path: Path,
    found: _Analysis,
    by_first: dict[str, list[ShortForm]],
    includes: dict[str, set[str]],
    checker: _Checker,
) -> Iterator[Finding]:
    theory = found.theory
    for index, command in enumerate(theory.commands):
        context = found.contexts[index]
        if not context.terms:
            continue
        bundles = _expand(context.bundles, includes)
        toks = list(significant(command.tokens(theory.tokens)))
        for k, tok in enumerate(toks):
            if tok.kind not in TEXTS or (k and toks[k - 1].text in _NOT_TERM_AFTER):
                continue
            text, start = term_text(tok)
            # `[where f = "..."]`, `[of "..."]`: a term with no surrounding type.
            instantiation = k > 0 and toks[k - 1].text in ("=", "of")
            inner = term_tokens(text)
            spelled = spelling(inner)
            variables = bound_names(inner) | context.variables
            consumed = 0
            for j, t in enumerate(inner):
                if j < consumed or t.kind is not Kind.WORD or t.text in variables:
                    continue
                if _field_name(inner, j):
                    continue
                best: tuple[ShortForm, int] | None = None
                for form in by_first.get(spelled[j], ()):
                    end = match(form.pattern, form.variables, inner, spelled, j)
                    if (
                        end is not None
                        and (best is None or end > best[1])
                        and _active(form, path, index, context, bundles, checker)
                    ):
                        best = form, end
                if best is None:
                    continue
                form, consumed = best
                if form.applied and not heads(inner, j):
                    continue
                if form.whole and not delimited(inner, j, consumed):
                    continue
                if form.overloaded and (instantiation or _passed_partially(inner, j, consumed)):
                    continue  # the generic name could not be resolved there
                if arguments(inner, consumed) >= form.arity:
                    written = " ".join(text[t.start : inner[consumed - 1].end].split())
                    yield Finding.at(
                        path,
                        theory.lines,
                        start + t.start,
                        form.code,
                        f"{written} is written out; {form.advice}",
                    )
