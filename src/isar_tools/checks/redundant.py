"""``redundant`` group: lemmas another lemma already states.

A lemma B is an instance of a lemma A when A's conclusion, its variables
replaced by arguments, is B's conclusion, and each of A's premises, so
replaced, is one of B's premises. B may have more premises. Then every use of
B can cite A, and B can go:

- ``duplicate-lemma``: A and B are instances of each other, the same
  statement up to the names of variables; reported on the later one;
- ``subsumed-lemma``: B is an instance of A only.

A statement is read lexically. Premises come from ``assumes`` and ``if``
(each one premise, a rule included), and from the conclusion's
``\\<lbrakk>A; B\\<rbrakk> \\<Longrightarrow> C``, and
``A \\<Longrightarrow> C``; ``\\<And>x.``, ``fixes``, and ``for`` fix
variables. Without types, a variable is a name fixed so, a schematic one
(``?x``), or a short free name (at most three characters, a symbol counting as
one) that no theory the lemma's theory imports declares a constant of, that is
no parameter of the lemma's locale or the locales it extends, and that is no
common HOL constant. Any other name is a
constant and matches only itself. A variable
matches one argument: a name, a literal, or a bracket group, so ``f x``
matches ``f (g y)`` but ``x`` does not match ``a + b`` unbracketed.

A is considered only where B could cite it: declared before B, in B's theory
or one it imports, at theory level or in a locale B's locale extends. Not
read: lemmas with several conclusions or ``obtains``, and B with an attribute
that registers it (``[simp]``), which A might not replace.

Anonymous and extended context blocks can add assumptions that are absent from
a lemma's written statement. A lemma from such a block is considered only inside
that same block or its nested blocks, never after it ends or in another theory.
Other unmodeled local-theory blocks receive the same conservative treatment;
their exported premises are not inferred. Plain named locale contexts retain
the locale-ancestry checks above.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.checks.terms import match, spelling, term_tokens
from isar_tools.checks.unused import INERT_ATTRIBUTES, attribute_names
from isar_tools.project.hierarchy import bracket_group, declarations
from isar_tools.project.model import Project
from isar_tools.project.names import entities
from isar_tools.project.workspace import SourceFile
from isar_tools.source.files import read_lenient
from isar_tools.source.keywords import CommandKind
from isar_tools.source.lexer import Kind, LineIndex, Token
from isar_tools.source.symbols import SYMBOL_RE
from isar_tools.source.theory import Theory, parse_theory, significant, unquote

_GOALS = frozenset({"lemma", "theorem", "corollary", "proposition"})
_ELEMENTS = frozenset({"fixes", "assumes", "shows", "if", "for", "includes", "notes"})
_IMPLIES = "\\<Longrightarrow>"
_ALL = "\\<And>"
# Common short constants of HOL, which a statement may use without the
# project declaring them.
_HOL_SHORT = frozenset(
    {
        "map",
        "set",
        "fst",
        "snd",
        "id",
        "Suc",
        "nat",
        "int",
        "abs",
        "min",
        "max",
        "sum",
        "hd",
        "tl",
        "rev",
        "zip",
        "dom",
        "ran",
        "inj",
        "the",
        "Max",
        "Min",
        "inf",
        "sup",
        "top",
        "bot",
        "mod",
        "div",
        "dvd",
        "Let",
        "If",
        "lfp",
        "gfp",
        "Inf",
        "Sup",
        "Pow",
        "Id",
        "o",
        "sgn",
        "gcd",
        "lcm",
        "fact",
        "of",
        "STR",
        "CHR",
        "Abs",
        "Rep",
        "Num",
        "One",
        "Some",
        "None",
        "True",
        "False",
        "Nil",
        "Inl",
        "Inr",
        "Pair",
        "nth",
        "last",
        "take",
        "drop",
        "fold",
        "all",
        "ex",
        "lex",
        "mono",
        "ord",
        "real",
        "rat",
        "exp",
        "ln",
        "log",
        "pi",
    }
)


@dataclass(frozen=True)
class Statement:
    """A lemma's premises and conclusion, as spelled tokens."""

    premises: tuple[tuple[str, ...], ...]
    conclusion: tuple[str, ...]
    variables: frozenset[str]
    tokens: tuple[tuple[Token, ...], ...]  # premises then conclusion, for matching


@dataclass(frozen=True)
class _Lemma:
    name: str
    path: Path
    line: int
    offset: int  # of its name
    index: int  # of its command
    scope: str  # its locale; "" at theory level
    contexts: tuple[int, ...]  # enclosing unmodeled block command indices, outermost first
    statement: Statement
    registers: bool  # carries a registering attribute
    lines: LineIndex


def _strip(toks: list[Token]) -> list[Token]:
    """``toks`` without brackets around all of it."""
    while len(toks) >= 2 and toks[0].text == "(" and toks[-1].text == ")":
        group, end = bracket_group(toks, 0)
        if end != len(toks):
            break
        toks = group[1:-1]
    return toks


def _top(toks: list[Token]) -> Iterator[tuple[int, str]]:
    """Indices and spellings of the tokens outside brackets."""
    depth = 0
    for i, tok in enumerate(toks):
        text = spelling([tok])[0]
        if text in ("(", "[", "{", "\\<lbrakk>"):
            depth += 1
        elif text in (")", "]", "}", "\\<rbrakk>"):
            depth -= 1
        elif depth == 0:
            yield i, text


def split_prop(toks: list[Token]) -> tuple[list[list[Token]], list[Token], set[str]]:
    """Premises, conclusion, and variables of the proposition ``toks``:
    ``\\<And>x. \\<lbrakk>A; B\\<rbrakk> \\<Longrightarrow> C``."""
    premises: list[list[Token]] = []
    variables: set[str] = set()
    toks = _strip(toks)
    while toks:
        texts = spelling(toks)
        if texts[0] == _ALL and "." in texts:
            dot = texts.index(".")
            variables.update(t.text for t in toks[1:dot] if t.kind is Kind.WORD)
            toks = _strip(toks[dot + 1 :])
            continue
        if texts[0] == "\\<lbrakk>":
            close = next((i for i, t in _top(toks) if i and t == _IMPLIES), -1)
            if close > 1 and texts[close - 1] == "\\<rbrakk>":
                inner = toks[1 : close - 1]
                cuts = [i for i, t in _top(inner) if t == ";"]
                for a, b in zip([-1, *cuts], [*cuts, len(inner)], strict=True):
                    premises.append(_strip(inner[a + 1 : b]))
                toks = _strip(toks[close + 1 :])
                continue
        arrow = next((i for i, t in _top(toks) if t == _IMPLIES), -1)
        if arrow < 0:
            break
        premises.append(_strip(toks[:arrow]))
        toks = _strip(toks[arrow + 1 :])
    return premises, toks, variables


def _props(toks: list[Token]) -> list[list[Token]]:
    """The propositions of an element: ``a: "A" "B" and "C"``."""
    return [term_tokens(unquote(t)) for t in toks if t.kind in (Kind.STRING, Kind.CARTOUCHE)]


def _fixed(toks: list[Token]) -> set[str]:
    """Names of ``x y :: T and z``."""
    names: set[str] = set()
    skip = False
    for tok in toks:
        if tok.text == "::":
            skip = True
        elif tok.text == "and":
            skip = False
        elif tok.kind is Kind.WORD and not skip:
            names.add(tok.text)
    return names


def _short(name: str) -> bool:
    shape = SYMBOL_RE.sub("x", name).rstrip("'0123456789")
    return len(shape) <= 3


def statement(args: list[Token], constants: frozenset[str]) -> Statement | None:
    """The statement of a goal command from after its name and attributes;
    None for several conclusions, ``obtains``, or ``defines``."""
    elements: dict[str, list[Token]] = {"shows": []}
    current = "shows"
    for tok in args:
        if tok.kind is Kind.WORD and tok.text in _ELEMENTS:
            current = tok.text
            elements.setdefault(current, [])
        elif tok.kind is Kind.WORD and tok.text in ("obtains", "defines"):
            return None
        else:
            elements[current].append(tok)
    shows = _props(elements["shows"])
    if len(shows) != 1:
        return None
    premises, conclusion, variables = split_prop(shows[0])
    # An assumption that is a rule (`\<And>x. A x \<Longrightarrow> B x`) is one premise.
    premises += [_strip(p) for e in ("assumes", "if") for p in _props(elements.get(e, []))]
    variables |= _fixed(elements.get("fixes", [])) | _fixed(elements.get("for", []))
    for tok in [t for p in [*premises, conclusion] for t in p]:
        name = tok.text
        if tok.kind is not Kind.WORD:
            continue
        if name[0].isdigit() or name[0] == "'":
            continue  # a numeral, or a type variable or the inside of a string ''abc
        if name.startswith("?") or (
            _short(name) and name not in constants and name not in _HOL_SHORT
        ):
            variables.add(name)
    if not conclusion:
        return None
    return Statement(
        tuple(tuple(spelling(p)) for p in premises),
        tuple(spelling(conclusion)),
        frozenset(variables),
        tuple(tuple(p) for p in [*premises, conclusion]),
    )


def instance(general: Statement, special: Statement) -> bool:
    """Whether ``special`` is an instance of ``general``."""
    if not any(t not in general.variables for t in general.conclusion):
        return False  # a conclusion that is just a variable says nothing
    toks = special.tokens[-1]
    bound: dict[str, tuple[str, ...]] = {}
    end = match(general.conclusion, general.variables, toks, special.conclusion, 0, bound)
    if end != len(toks):
        return False
    return _premises(list(general.premises), general.variables, special, bound)


def _premises(
    wanted: list[tuple[str, ...]],
    variables: frozenset[str],
    special: Statement,
    bound: dict[str, tuple[str, ...]],
) -> bool:
    """Whether each of ``wanted`` matches a premise of ``special`` under
    ``bound``, extended consistently; tries every choice."""
    if not wanted:
        return True
    first, rest = wanted[0], wanted[1:]
    for toks, spelled in zip(special.tokens, special.premises, strict=False):
        attempt = dict(bound)
        if match(first, variables, toks, spelled, 0, attempt) == len(toks) and _premises(
            rest, variables, special, attempt
        ):
            return True
    return False


def _registers(args: list[Token]) -> bool:
    if not args or args[0].text != "[":
        return False
    group, _ = bracket_group(args, 0)
    return any(name not in INERT_ATTRIBUTES for name in attribute_names(group))


def _contexts(theory: Theory) -> dict[int, tuple[int, ...]]:
    """Keep unmodeled local assumptions inside the blocks that introduce them."""
    stack: list[tuple[int, bool]] = []
    contexts: dict[int, tuple[int, ...]] = {}
    for i, command in enumerate(theory.commands):
        if command.name == "end":
            if stack:
                stack.pop()
            continue
        contexts[i] = tuple(index for index, opaque in stack if opaque)
        if command.kind is not CommandKind.THY_DECL_BLOCK:
            continue
        toks = list(significant(command.tokens(theory.tokens)))
        if toks[-1].text != "begin":
            continue
        # Only these named scopes are modeled by _Checker.parents and Entity.scope.
        named = command.name in {"locale", "class"} or (
            command.name == "context" and len(toks) == 3
        )
        stack.append((i, not named))
    return contexts


def _lemmas(theory: Theory, path: Path, checker: "_Checker") -> Iterator[_Lemma]:
    """The lemmas of ``theory``, read from ``path``."""
    name = theory.header.name.text if theory.header else path.stem
    contexts = _contexts(theory)
    for e in entities(theory, name, path):
        if e.kind != "fact" or e.member or e.command not in _GOALS:
            continue
        index = e.command_index
        toks = list(significant(theory.commands[index].tokens(theory.tokens)))
        at = next(i for i, t in enumerate(toks) if unquote(t) == e.name)
        rest = toks[at + 1 :]
        registers = _registers(rest)
        if rest[0].text == "[":
            rest = rest[bracket_group(rest, 0)[1] :]
        found = statement(rest[1:], checker.in_context(e.scope, path))  # after the `:`
        if found is not None:
            offset = toks[at].start
            yield _Lemma(
                e.name,
                path,
                e.line,
                offset,
                index,
                e.scope,
                contexts[index],
                found,
                registers,
                theory.lines,
            )


class _Checker:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.parents: dict[str, set[str]] = {}
        self.constants: dict[Path, set[str]] = {}  # theory -> what it declares
        self.parameters: dict[str, set[str]] = {}  # locale -> its parameters
        self._visible: dict[Path, frozenset[Path]] = {}
        self._imported: dict[Path, frozenset[str]] = {}
        self._in_context: dict[tuple[str, Path], frozenset[str]] = {}

    def visible(self, path: Path) -> frozenset[Path]:
        if path not in self._visible:
            session = self.project.session_of(path)
            self._visible[path] = frozenset(self.project.closure([path], session))
        return self._visible[path]

    def ancestors(self, locale: str) -> set[str]:
        seen: set[str] = set()
        stack = [locale]
        while stack:
            name = stack.pop()
            if name and name not in seen:
                seen.add(name)
                stack += self.parents.get(name, ())
        return seen

    def in_context(self, locale: str, path: Path) -> frozenset[str]:
        """The constants of a lemma in ``locale`` of the theory ``path``: those
        the theory and its imports declare, and the parameters of the locale
        and the locales it extends."""
        if path not in self._imported:
            declared = (self.constants.get(p, set()) for p in self.visible(path))
            self._imported[path] = frozenset(name for names in declared for name in names)
        key = (locale, path)
        if key not in self._in_context:
            local = (self.parameters.get(a, set()) for a in self.ancestors(locale))
            self._in_context[key] = self._imported[path].union(*local)
        return self._in_context[key]

    def citable(self, general: _Lemma, special: _Lemma) -> bool:
        """Whether ``special``'s context can cite ``general``."""
        if general.contexts and (
            general.path != special.path
            or special.contexts[: len(general.contexts)] != general.contexts
        ):
            return False
        if general.path == special.path:
            if general.index >= special.index:
                return False
        elif general.path not in self.visible(special.path):
            return False
        return not general.scope or general.scope in self.ancestors(special.scope)


def _key(lemma: _Lemma) -> str:
    """The first token of the conclusion, or ``*`` for a variable."""
    first = lemma.statement.conclusion[0]
    return "*" if first in lemma.statement.variables else first


def check_redundant(sources: Iterable[SourceFile]) -> list[Finding]:
    by_project: dict[int, tuple[Project, list[Path]]] = {}
    for source in sources:
        by_project.setdefault(id(source.project), (source.project, []))[1].append(source.path)
    findings: list[Finding] = []
    for project, paths in by_project.values():
        checker = _Checker(project)
        universe = list(dict.fromkeys(project.closure([*paths, *project.theory_files()], None)))
        theories = {p: parse_theory(read_lenient(p), project.keywords_for(p)) for p in universe}
        for path, theory in theories.items():
            name = theory.header.name.text if theory.header else path.stem
            for e in entities(theory, name, path):
                if e.kind == "constant":
                    # A locale's parameters are constants only in its context.
                    local = e.command in ("fixes", "for") and not e.scope.endswith("_class")
                    target = (
                        checker.parameters.setdefault(e.scope, set())
                        if local
                        else checker.constants.setdefault(path, set())
                    )
                    target.add(e.name)
                    # The words and symbols of its notation: `\<gamma>` for `gamma`.
                    target.update(spelling(term_tokens(e.notation)))
            for decl in declarations(theory, path):
                extra = decl.sorts if decl.kind == "class" else []
                checker.parents.setdefault(decl.name, set()).update(decl.parents, extra)
        lemmas = [lemma for p, t in theories.items() for lemma in _lemmas(t, p, checker)]
        by_key: dict[str, list[_Lemma]] = {}
        for lemma in lemmas:
            by_key.setdefault(_key(lemma), []).append(lemma)
        checked = set(paths)
        for special in lemmas:
            if special.path in checked and not special.registers:
                findings += _redundancy(special, by_key, checker)
    return findings


def _redundancy(
    special: _Lemma, by_key: dict[str, list[_Lemma]], checker: _Checker
) -> Iterator[Finding]:
    key = special.statement.conclusion[0]
    candidates = [*by_key.get(key, ()), *by_key.get("*", ())]
    # Cite upstream: another theory's lemma before one of the same theory.
    candidates.sort(key=lambda g: (g.path == special.path, str(g.path), g.line))
    for general in candidates:
        if general is special or not checker.citable(general, special):
            continue
        if not instance(general.statement, special.statement):
            continue
        where = f"{general.path.name}:{general.line}"
        if instance(special.statement, general.statement):
            code = "duplicate-lemma"
            message = f"{special.name} states {general.name} ({where}) again"
        else:
            code = "subsumed-lemma"
            message = f"{special.name} is an instance of {general.name} ({where}); cite it instead"
        yield Finding.at(special.path, special.lines, special.offset, code, message)
        return
