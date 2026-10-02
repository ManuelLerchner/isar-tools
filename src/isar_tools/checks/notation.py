"""``notation`` group: a constant written out where it has a short form.

A project gives a constant a short form in four ways, and once it has, every
later term should use it:

- a mixfix on its declaration (``definition``, ``fun``, ``consts``, a class or
  locale parameter, a record field, ...): ``f x`` should be written in that
  mixfix;
- a ``notation f (mixfix)`` command, likewise (``notation (input)`` counts,
  other print modes do not);
- ``adhoc_overloading g == f``: ``f x`` should be written ``g x``. An
  instance that is a term (``"lift f"``) is matched as that token sequence;
- any of these inside ``bundle B begin ... end``: the short form holds where
  ``B`` is open, by ``unbundle B`` (until ``unbundle no B``), ``open_bundle``,
  ``includes B``, ``including B``, or a bundle that unbundles ``B``.

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
from isar_tools.checks.locales import TERM_KEYWORDS, bound_names, term_text
from isar_tools.project.hierarchy import bracket_group, declarations, parse_mixfix
from isar_tools.project.model import Project
from isar_tools.project.names import entities
from isar_tools.project.notation import INFIX, NotationError, template
from isar_tools.project.workspace import SourceFile
from isar_tools.source.files import read_source
from isar_tools.source.keywords import DOCUMENT, CommandKind
from isar_tools.source.lexer import IDENTIFIER_RE, IGNORABLE, Kind, Token, tokenize
from isar_tools.source.symbols import encode
from isar_tools.source.theory import Command, Theory, parse_theory, significant, unquote

CODE = "spelled-out-notation"

# Commands whose strings and cartouches are no terms of the theory.
_NO_TERMS = frozenset(
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
_TERMS = frozenset({Kind.STRING, Kind.CARTOUCHE})
# Elements that fix variables, and the words that end the variables.
_FIXING = frozenset({"fixes", "for", "fix", "obtain", "obtains", "define"})
_FIXED_END = frozenset(
    {"where", "assumes", "shows", "obtains", "if", "when", "begin", "defines", "notes"}
)
_INCLUDING = frozenset({"includes", "including"})
# Infix words of HOL: what follows them is no argument of the name before.
_INFIX_WORDS = frozenset({"o", "div", "mod", "dvd"})
_OPENERS = frozenset({"(", "[", "{", "\\<lparr>"})
_CLOSERS = frozenset({")", "]", "}", "\\<rparr>"})


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
            yield ShortForm(pattern, advice, 1, scope, path, index)


def _declared_forms(theory: Theory, path: Path) -> Iterator[ShortForm]:
    """Short forms from the mixfix of a declaration."""
    name = theory.header.name.text if theory.header else path.stem
    for e in entities(theory, name, path):
        if e.kind != "constant" or not e.mixfix or e.mode == "output":
            continue
        shown = _shown(e.mixfix, e.notation)
        if shown is None:
            continue
        parameter = e.member and e.command in ("fixes", "for")
        if parameter and e.scope.endswith("_class"):
            scope = Scope("global")  # a class parameter is a global constant
        elif e.scope and (parameter or not e.member):
            scope = Scope("locale", e.scope)
        else:
            scope = Scope("global")
        advice = f"its notation is {shown[0]}"
        index = e.command_index
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
    forms: list[ShortForm] = []
    includes: dict[str, set[str]] = {}
    for i, command in enumerate(theory.commands):
        toks = _tokens(theory, command)
        args = toks[1:]
        if command.kind is CommandKind.THY_END:
            if stack:
                stack.pop()
            contexts.append(_NO_CONTEXT)
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
                and command.name not in _NO_TERMS
                and "ML" not in command.name,
            )
        )
        scope = _scope(stack)
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
    forms += _declared_forms(theory, path)
    return _Analysis(theory, contexts, frozenset(opened), forms, includes)


def _atom(tok: Token) -> bool:
    """Whether ``tok`` is an argument by itself: a name, a literal, ``_``."""
    if tok.kind is Kind.WORD:
        return tok.text not in TERM_KEYWORDS and tok.text not in _INFIX_WORDS
    return tok.kind in _TERMS or tok.text == "_" or bool(IDENTIFIER_RE.fullmatch(encode(tok.text)))


def _head(toks: list[Token], i: int) -> bool:
    """Whether ``toks[i]`` heads an application: application associates to
    the left, so in ``g f x`` the name ``f`` is an argument of ``g``."""
    return i == 0 or not (_atom(toks[i - 1]) or encode(toks[i - 1].text) in _CLOSERS)


def _field_name(toks: list[Token], i: int) -> bool:
    r"""Whether ``toks[i]`` names a record field to update or construct:
    ``r\<lparr>f := x\<rparr>``, ``\<lparr>f = x, g = y\<rparr>``."""
    after = "".join(t.text for t in toks[i + 1 : i + 3])
    before = encode(toks[i - 1].text) if i else ""
    # `:=` lexes as `:` and `=`; `(|` as `(` and `|`.
    return after == ":=" or (after[:1] == "=" and before in ("\\<lparr>", "|", ","))


def _arguments(toks: list[Token], i: int) -> int:
    """How many arguments follow at ``toks[i]``; a bracket group is one."""
    count = 0
    while i < len(toks) and (_atom(toks[i]) or encode(toks[i].text) in _OPENERS):
        depth = 0
        while i < len(toks):
            text = encode(toks[i].text)
            depth += (text in _OPENERS) - (text in _CLOSERS)
            i += 1
            if depth <= 0:
                break
        count += 1
    return count


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
        theory = parse_theory(read_source(path), self.project.keywords_for(path))
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
                if " ".join(form.pattern) not in checker.allow:
                    by_first.setdefault(form.pattern[0], []).append(form)
        for path in paths:
            found = checker.analyses[path]
            assert found is not None  # set once the import cycle guard is left
            findings += _check(path, found, by_first, includes, checker)
    return findings


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
            if tok.kind not in _TERMS or (k and toks[k - 1].text in _NOT_TERM_AFTER):
                continue
            text, start = term_text(tok)
            inner = [t for t in tokenize(text) if t.kind not in IGNORABLE]
            spelled = [encode(t.text) for t in inner]
            variables = bound_names(inner) | context.variables
            consumed = 0
            for j, t in enumerate(inner):
                if j < consumed or t.kind is not Kind.WORD or t.text in variables:
                    continue
                if _field_name(inner, j):
                    continue
                best: ShortForm | None = None
                for form in by_first.get(spelled[j], ()):
                    n = len(form.pattern)
                    if (
                        tuple(spelled[j : j + n]) == form.pattern
                        and (best is None or n > len(best.pattern))
                        and _active(form, path, index, context, bundles, checker)
                    ):
                        best = form
                if best is None:
                    continue
                consumed = j + len(best.pattern)
                needs = best.arity
                if not needs or (_head(inner, j) and _arguments(inner, consumed) >= needs):
                    written = text[t.start : inner[consumed - 1].end]
                    yield Finding.at(
                        path,
                        theory.lines,
                        start + t.start,
                        CODE,
                        f"{written} is written out; {best.advice}",
                    )
