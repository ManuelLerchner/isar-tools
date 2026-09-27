"""Parser for Isabelle session ``ROOT`` files.

Uses the outer-syntax lexer, so a name is exactly one token: a word, a quoted
string, or a cartouche. An unquoted ``HOL-Library`` is three tokens and is
reported, as Isabelle rejects it too. Every parse problem becomes a
``Diagnostic``; the parser recovers at the next session and never raises.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

from isar_tools.source.lexer import Kind, LineIndex, Token, tokenize
from isar_tools.source.theory import Name, significant, unquote

# Keywords that start a clause of a session body, or a new ROOT entry.
BODY_KEYWORDS = frozenset(
    {
        "description",
        "options",
        "sessions",
        "directories",
        "theories",
        "document_theories",
        "document_files",
        "export_files",
        "export_classpath",
    }
)
ENTRY_KEYWORDS = frozenset({"session", "chapter", "chapter_definition"})
_NAME_KINDS = frozenset({Kind.WORD, Kind.STRING, Kind.CARTOUCHE})
_GLUE_KINDS = frozenset({Kind.WORD, Kind.SYM_IDENT, Kind.DELIM})
_STRUCTURAL = frozenset({"(", ")", "[", "]", ",", "=", "+"})


@dataclass(frozen=True)
class Diagnostic:
    message: str
    start: int


@dataclass(frozen=True)
class TheoryEntry:
    name: Name
    global_: bool = False
    options: str = ""  # raw text of the `theories [...]` options, if any


@dataclass
class RootSession:
    name: Name
    chapter: str
    groups: list[str] = field(default_factory=list[str])
    dir: Name | None = None
    parent: Name | None = None
    description: str = ""
    options: str = ""
    sessions: list[Name] = field(default_factory=list[Name])
    directories: list[Name] = field(default_factory=list[Name])
    theories: list[TheoryEntry] = field(default_factory=list[TheoryEntry])
    document_theories: list[Name] = field(default_factory=list[Name])
    document_files: list[Name] = field(default_factory=list[Name])
    export_files: list[Name] = field(default_factory=list[Name])


@dataclass
class RootFile:
    path: Path | None
    text: str
    sessions: list[RootSession]
    diagnostics: list[Diagnostic]
    lines: LineIndex = field(repr=False)


class _Stop(Exception):
    """Abandon the current ROOT entry after a reported error."""


class _Parser:
    def __init__(self, text: str, tokens: list[Token]) -> None:
        self.text = text
        self.toks = list(significant(tokens))
        self.i = 0
        self.diagnostics: list[Diagnostic] = []

    def peek(self) -> Token | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def at(self, *texts: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.text in texts and tok.kind is not Kind.STRING

    def advance(self) -> Token:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def error(self, message: str) -> NoReturn:
        """Report ``message`` at the current token and abandon the entry."""
        tok = self.peek()
        start = tok.start if tok is not None else (self.toks[-1].end if self.toks else 0)
        self.diagnostics.append(Diagnostic(message, start))
        raise _Stop

    def is_name(self) -> bool:
        tok = self.peek()
        if tok is None or tok.kind not in _NAME_KINDS:
            return False
        return tok.kind is not Kind.WORD or tok.text not in BODY_KEYWORDS | ENTRY_KEYWORDS

    def name(self, what: str) -> Name:
        if not self.is_name():
            self.error(f"expected {what}")
        tok = self.advance()
        if tok.kind is not Kind.WORD:
            return Name(unquote(tok), tok.start)
        # An unquoted name with `-` or `/` lexes as several adjacent tokens.
        # Isabelle rejects it; report it once and read it as one name.
        text = tok.text
        end = tok.end
        while (nxt := self.peek()) is not None and nxt.start == end and nxt.kind in _GLUE_KINDS:
            if nxt.kind is not Kind.WORD and nxt.text in _STRUCTURAL:
                break
            text += nxt.text
            end = nxt.end
            self.advance()
        if text != tok.text:
            self.diagnostics.append(
                Diagnostic(
                    f"{what} {text} must be quoted: unquoted, it is several tokens", tok.start
                )
            )
        return Name(text, tok.start)

    def names(self, what: str) -> list[Name]:
        if not self.is_name():
            self.error(f"expected at least one {what}")
        names: list[Name] = []
        while self.is_name():
            names.append(self.name(what))
        return names

    def bracketed(self, open_: str, close: str) -> str:
        """Skip a balanced ``open_ ... close`` group; return its source slice."""
        start = self.advance()
        depth = 1
        last = start
        while self.peek() is not None and depth:
            last = self.advance()
            depth += {open_: 1, close: -1}.get(last.text, 0)
        if depth:
            self.error(f"unterminated {open_}")
        return self.text[start.start : last.end]

    def skip_to_entry(self) -> None:
        while self.peek() is not None and not self.at(*ENTRY_KEYWORDS):
            self.advance()

    def parse(self) -> Iterator[RootSession]:
        chapter = "Unsorted"
        while (tok := self.peek()) is not None:
            try:
                if self.at("chapter_definition"):
                    self.advance()
                    self.name("chapter name")
                    if self.at("("):
                        self.bracketed("(", ")")
                    if self.at("description"):
                        self.advance()
                        self.name("description")
                elif self.at("chapter"):
                    self.advance()
                    chapter = self.name("chapter name").text
                elif self.at("session"):
                    yield self.session(chapter)
                else:
                    self.error(f"unexpected {tok.text!r}; expected session or chapter")
            except _Stop:
                if self.peek() is tok:
                    self.advance()
                self.skip_to_entry()

    def session(self, chapter: str) -> RootSession:
        self.advance()
        session = RootSession(self.name("session name"), chapter)
        try:
            if self.at("("):
                self.advance()
                while self.is_name():
                    session.groups.append(self.advance().text)
                if not self.at(")"):
                    self.error("expected ) after session groups")
                self.advance()
            if self.at("in"):
                self.advance()
                session.dir = self.name("session directory")
            if not self.at("="):
                self.error("expected = after session name")
            self.advance()
            if self.is_name():
                parent = self.name("parent session")
                if not self.at("+"):
                    self.error("expected + after parent session")
                self.advance()
                session.parent = parent
            self.body(session)
        except _Stop:
            self.skip_to_entry()
        return session

    def body(self, session: RootSession) -> None:
        while (tok := self.peek()) is not None and not self.at(*ENTRY_KEYWORDS):
            keyword = tok.text if tok.kind is Kind.WORD else ""
            self.advance()
            if keyword == "description":
                session.description = self.name("description").text
            elif keyword == "options":
                session.options = self.options()
            elif keyword == "sessions":
                session.sessions += self.names("session name")
            elif keyword == "directories":
                session.directories += self.names("directory")
            elif keyword == "theories":
                options = self.options() if self.at("[") else ""
                session.theories += self.theory_entries(options)
            elif keyword == "document_theories":
                session.document_theories += self.names("theory name")
            elif keyword in ("document_files", "export_files"):
                if self.at("("):
                    self.bracketed("(", ")")
                if keyword == "export_files" and self.at("["):
                    self.bracketed("[", "]")
                files = self.names("file name")
                target = (
                    session.document_files if keyword == "document_files" else session.export_files
                )
                target += files
            elif keyword == "export_classpath":
                while self.is_name():
                    self.advance()
            else:
                self.i -= 1
                self.error(f"unexpected {tok.text!r} in session {session.name.text}")

    def options(self) -> str:
        if not self.at("["):
            self.error("expected [ after options")
        return self.bracketed("[", "]")

    def theory_entries(self, options: str) -> list[TheoryEntry]:
        if not self.is_name():
            self.error("expected at least one theory name")
        entries: list[TheoryEntry] = []
        while self.is_name():
            name = self.name("theory name")
            global_ = False
            if self.at("("):
                self.advance()
                if not self.at("global"):
                    self.error("expected global")
                self.advance()
                if not self.at(")"):
                    self.error("expected ) after global")
                self.advance()
                global_ = True
            entries.append(TheoryEntry(name, global_, options))
        return entries


def parse_root(text: str, path: Path | None = None) -> RootFile:
    tokens = tokenize(text)
    parser = _Parser(text, tokens)
    sessions = list(parser.parse())
    diagnostics = parser.diagnostics
    for tok in tokens:
        if tok.kind is Kind.ERROR:
            diagnostics.append(Diagnostic("unterminated comment, string, or cartouche", tok.start))
    diagnostics.sort(key=lambda d: d.start)
    return RootFile(path, text, sessions, diagnostics, LineIndex(text))


def read_root(path: Path) -> RootFile:
    return parse_root(path.read_text(encoding="utf-8"), path)
