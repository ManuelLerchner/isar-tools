"""Free variables in locale headers (group ``locales``, opt-in).

Inside the terms of a ``locale`` or ``context`` header, Isabelle reads an
unknown identifier as a free variable and generalizes over it. An assumption
that cites a deleted or misspelt constant therefore still builds, but holds
for an arbitrary value of that name and constrains nothing.

Without running Isabelle the check approximates the name space:

- *local* names: the parameters of the header (``fixes``, the ``for`` clause,
  ``defines``), the parameters of every locale or class it extends, resolved
  through the imports of its theory, the words of their mixfix notations, and,
  for an unnamed ``context``, the parameters of the enclosing blocks;
- *bound* names: variables after a binder (``\\<And>``, ``\\<forall>``,
  ``\\<exists>``, ``\\<lambda>``, ``THE``, ``{x. ...}``, ``let``, ...) up to its
  ``.``. They are bound for the whole term, not only for the binder's scope;
- *known* names: every identifier that occurs outside ``locale`` and
  ``context`` headers, document text, and comments, in any theory of the
  project or of the included (``-d``) theories it imports. This covers the
  project's definitions, and also uses of the constants of Isabelle's own
  sessions, which are not visible without Isabelle.

An identifier of a term that is none of these is reported. Inner syntax is only
approximated: terms are split into identifiers lexically, type annotations
(``x :: T``) are skipped, and qualified names (``List.map``) are not checked.
To keep short, deliberately free names out, only identifiers of at least four
characters that contain an underscore (or ``\\<^sub>``) are reported. A symbol
(``\\<gamma>``) counts as one character.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.project.hierarchy import (
    Declaration,
    Located,
    Parameter,
    closure,
    declarations,
    parse_context,
    parse_declaration,
)
from isar_tools.project.model import Project
from isar_tools.project.workspace import NO_SESSION, SourceFile
from isar_tools.source.files import read_source
from isar_tools.source.keywords import DOCUMENT, CommandKind
from isar_tools.source.lexer import IDENTIFIER_RE, IGNORABLE, Kind, LineIndex, Token, tokenize
from isar_tools.source.symbols import SYMBOL_RE, TO_ASCII
from isar_tools.source.theory import Theory, parse_theory, significant, unquote

MIN_LENGTH = 4

# Symbols and words that bind the variables up to the next `.`.
_BINDER_SYMBOLS = frozenset(
    {
        "\\<And>",
        "\\<forall>",
        "\\<exists>",
        "\\<nexists>",
        "\\<lambda>",
        "\\<Union>",
        "\\<Inter>",
        "\\<Sum>",
        "\\<Prod>",
        "\\<Squnion>",
        "\\<Sqinter>",
        "\\<some>",
        "\\<iota>",
        "%",
        "!!",
    }
)
_BINDER_WORDS = frozenset(
    {"ALL", "EX", "EX1", "THE", "SOME", "LEAST", "GREATEST", "INF", "SUP", "UNION", "INTER"}
)
# Words of HOL's term syntax that are never variables.
TERM_KEYWORDS = _BINDER_WORDS | {"let", "in", "if", "then", "else", "case", "of"}
# Tokens that may occur in a type after `::` without ending it.
_TYPE_OPERATORS = frozenset({"=>", "\\<Rightarrow>", "*", "\\<times>", "+", "::", "~=>"})
_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = frozenset(_OPEN.values())
_MIXFIX_ESCAPE = re.compile(r"'(.)")
_HEADERS = frozenset({"locale", "context"})


def _normal(tok: Token) -> str:
    return TO_ASCII.get(tok.text, tok.text)


def _binder_vars(toks: list[Token], i: int) -> list[str]:
    """Variables bound by a binder whose variables start at ``toks[i]``:
    words, possibly in a tuple pattern or with type annotations, up to ``.``."""
    names: list[str] = []
    typing = False
    if i < len(toks) and toks[i].text == "!":
        i += 1  # \<exists>!x
    for tok in toks[i:]:
        if tok.kind is Kind.WORD:
            if not typing:
                names.append(tok.text.split(".")[0])  # `x.P` lexes as one word
                if "." in tok.text:
                    break
        elif tok.text == "::":
            typing = True
        elif tok.text in ("(", ")", ","):
            typing = False
        elif not (typing and _normal(tok) in _TYPE_OPERATORS):
            break
    return names


def _set_builder_vars(toks: list[Token], i: int) -> list[str]:
    """Variables of ``{x. P}`` or ``{t | x y. P}`` opened at ``toks[i]``."""
    depth = 0
    bar = -1
    for j in range(i, len(toks)):
        text = toks[j].text
        if text in _OPEN:
            depth += 1
        elif text in _CLOSE:
            depth -= 1
            if depth == 0:
                return []
        elif depth == 1 and text == "|" and bar < 0:
            bar = j
        elif depth == 1 and text == ".":
            return _binder_vars(toks, (bar if bar >= 0 else i) + 1)
    return []


def _let_vars(toks: list[Token], i: int) -> list[str]:
    """Variables of ``let x = a; (y, z) = b in ...`` after the ``let`` at ``i``."""
    names: list[str] = []
    depth = 0
    start = True  # at the start of a binding
    for j in range(i + 1, len(toks)):
        text = toks[j].text
        if start:
            names += _binder_vars(toks, j)
            start = False
        if text in _OPEN:
            depth += 1
        elif text in _CLOSE:
            depth -= 1
        if depth < 0 or (depth == 0 and text == "in"):
            break
        start = depth == 0 and text == ";"
    return names


def bound_names(toks: list[Token]) -> set[str]:
    bound: set[str] = set()
    for i, tok in enumerate(toks):
        if _normal(tok) in _BINDER_SYMBOLS or (tok.kind is Kind.WORD and tok.text in _BINDER_WORDS):
            bound.update(_binder_vars(toks, i + 1))
        elif tok.text == "let":
            bound.update(_let_vars(toks, i))
        elif tok.text == "{":
            bound.update(_set_builder_vars(toks, i))
    return bound


def _free_words(toks: list[Token]) -> Iterator[Token]:
    """Words of a term outside type annotations."""
    depth = 0
    typed_at = -1  # bracket depth of the `::` whose type is being skipped
    previous: Token | None = None
    for tok in toks:
        # A word glued to a control symbol belongs to notation: `+\<^sub>M`.
        glued = (
            previous is not None and previous.end == tok.start and previous.text.startswith("\\<^")
        )
        previous = tok
        text = _normal(tok)
        if text in _OPEN:
            depth += 1
        elif text in _CLOSE:
            depth -= 1
            if depth < typed_at:
                typed_at = -1
        elif text == "::":
            typed_at = depth if typed_at < 0 else typed_at
        elif typed_at == depth and tok.kind is not Kind.WORD and text not in _TYPE_OPERATORS:
            typed_at = -1
        if tok.kind is Kind.WORD and typed_at < 0 and not glued:
            yield tok


def term_identifiers(text: str) -> Iterator[tuple[str, int]]:
    """Identifiers of the term ``text`` that may be free, with their offsets:
    not bound, not in a type annotation, not schematic, not qualified."""
    toks = [t for t in tokenize(text) if t.kind not in IGNORABLE]
    skip = bound_names(toks) | TERM_KEYWORDS
    for tok in _free_words(toks):
        name = tok.text
        if name[0] in "?'" or name[0].isdigit() or "." in name or name in skip:
            continue
        yield name, tok.start


def reportable(name: str, min_length: int = MIN_LENGTH) -> bool:
    """The heuristic filter: long enough and with an underscore; ``\\<^sub>``
    counts as an underscore and any other symbol as one character."""
    shape = name.replace("\\<^sub>", "_").replace("\\<^isub>", "_")
    shape = SYMBOL_RE.sub(lambda m: "" if m.group(0).startswith("\\<^") else "x", shape)
    return len(shape) >= min_length and "_" in shape


def term_text(tok: Token) -> tuple[str, int]:
    """The text of a term token and the offset where it starts."""
    text = unquote(tok)
    # The opening delimiter is half of what unquoting removed: `"`, `‹`, or
    # `\<open>` (7 of the 15 characters of `\<open>` and `\<close>`).
    return text, tok.start + (len(tok.text) - len(text)) // 2


def _parameter_names(params: Iterable[Parameter]) -> set[str]:
    names: set[str] = set()
    for p in params:
        names.add(p.name)
        # In mixfix, `'` escapes the next character: `+\<^sub>'_\<^sub>1`.
        names.update(IDENTIFIER_RE.findall(_MIXFIX_ESCAPE.sub(r"\1", p.notation)))
    return names


def own_names(decl: Declaration) -> set[str]:
    """Names a header declares itself: parameters, their notation, and the
    constants of its ``defines``."""
    names = _parameter_names([*decl.fixes, *decl.for_fixes])
    for d in decl.defines:
        for prop in d.props[:1]:
            names.update(n for n, _ in list(term_identifiers(prop))[:1])
    return names


@dataclass
class _Header:
    """A header to check, with the blocks enclosing it (innermost last)."""

    decl: Declaration
    enclosing: list[Declaration]


@dataclass
class _Theory:
    path: Path
    lines: LineIndex
    headers: list[_Header] = field(default_factory=list[_Header])


def _known_names(theory: Theory) -> set[str]:
    """Identifiers outside locale and context headers, document text, and
    comments."""
    names: set[str] = set()
    for command in theory.commands:
        if command.name in _HEADERS or command.kind in DOCUMENT:
            continue
        text = " ".join(t.text for t in significant(command.tokens(theory.tokens)))
        names.update(IDENTIFIER_RE.findall(text))
    return names


def _headers(theory: Theory, path: Path) -> list[_Header]:
    """``locale`` and unnamed ``context`` headers with terms, and the blocks
    enclosing each. A command ending in ``begin`` opens a block, ``end``
    closes one."""
    found: list[_Header] = []
    stack: list[Declaration | None] = []
    for command in theory.commands:
        if command.kind is CommandKind.THY_END:
            if stack:
                stack.pop()
            continue
        decl = parse_declaration(theory, command, path) or parse_context(theory, command, path)
        if decl is not None and decl.terms and (decl.kind == "locale" or not decl.parents):
            enclosing = [d for d in stack if d is not None] if decl.kind == "context" else []
            found.append(_Header(decl, enclosing))
        toks = command.tokens(theory.tokens)
        last = next((t for t in reversed(toks) if t.kind not in IGNORABLE), None)
        if command.kind is not CommandKind.THY_BEGIN and last is not None and last.text == "begin":
            stack.append(decl)
    return found


class _Checker:
    def __init__(self, project: Project, allow: frozenset[str], min_length: int) -> None:
        self.project = project
        self.allow = allow
        self.min_length = min_length
        self.index: dict[str, list[Located]] = {}
        self.known: set[str] = set()
        self._visible: dict[Path, set[Path]] = {}

    def visible(self, path: Path) -> set[Path]:
        if path not in self._visible:
            self._visible[path] = set(self.project.closure([path], self.project.session_of(path)))
        return self._visible[path]

    def read(self, path: Path, checked: bool) -> _Theory | None:
        theory = parse_theory(read_source(path), self.project.keywords_for(path))
        session = self.project.session_of(path)
        name, external = (session.name, session.external) if session else (NO_SESSION, False)
        for decl in declarations(theory, path):
            self.index.setdefault(decl.name, []).append(Located(decl, name, external))
        self.known |= _known_names(theory)
        # A locale with assumptions defines a predicate of its name.
        self.known.update(self.index)
        return _Theory(path, theory.lines, _headers(theory, path)) if checked else None

    def names(self, decl: Declaration) -> set[str]:
        """Parameters of ``decl`` and of everything it extends."""
        names = own_names(decl)
        found, _ = closure(self.index, decl.parents, self.visible, decl.path)
        for located in found:
            names |= own_names(located.decl)
        return names

    def check(self, theory: _Theory) -> Iterator[Finding]:
        for header in theory.headers:
            decl = header.decl
            local = self.names(decl)
            for outer in header.enclosing:
                local |= self.names(outer)
            what = f"locale {decl.name}" if decl.kind == "locale" else "context"
            for tok in decl.terms:
                text, start = term_text(tok)
                for name, offset in term_identifiers(text):
                    if (
                        name in local
                        or name in self.known
                        or name in self.allow
                        or not reportable(name, self.min_length)
                    ):
                        continue
                    yield Finding.at(
                        theory.path,
                        theory.lines,
                        start + offset,
                        "locale-free-variable",
                        f"{name} in the header of {what} is no parameter, bound variable, "
                        "or name used elsewhere; Isabelle generalizes over it as a free variable",
                    )


def check_locales(
    sources: Iterable[SourceFile],
    *,
    allow: Iterable[str] = (),
    min_length: int = MIN_LENGTH,
) -> list[Finding]:
    """Free-variable findings in the ``locale`` and ``context`` headers of
    ``sources``. Names are known from every theory of each source's project
    and from the included theories those import."""
    by_project: dict[int, tuple[Project, list[Path]]] = {}
    for source in sources:
        by_project.setdefault(id(source.project), (source.project, []))[1].append(source.path)
    findings: list[Finding] = []
    for project, paths in by_project.values():
        checker = _Checker(project, frozenset(allow), min_length)
        start = [*paths, *project.theory_files()]
        universe = list(dict.fromkeys(project.closure(start, None)))
        checked = set(paths)
        theories = [checker.read(path, path in checked) for path in universe]
        for theory in theories:
            if theory is not None:
                findings += checker.check(theory)
    return findings
