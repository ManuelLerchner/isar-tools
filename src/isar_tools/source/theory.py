"""Theory files as a header, a sequence of commands, and goal blocks.

Built on the lossless token stream: every command is a contiguous token range,
so tools can inspect or rewrite layout between tokens without touching the
tokens themselves.
"""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.source.keywords import (
    BUILTIN_COMMANDS,
    KIND_NAMES,
    PROOF_GOALS,
    PROOF_KINDS,
    PROOF_TERMINATORS,
    THEORY_GOALS,
    CommandKind,
    commands_of_import,
)
from isar_tools.source.lexer import IGNORABLE, Kind, LineIndex, Token, iter_tokens, tokenize

# Markers that turn the following cartouche into a formal comment.
COMMENT_MARKERS = frozenset({"\\<comment>", "\\<^cancel>", "\\<^marker>", "―", "⌦", "✐"})
_NAME_KINDS = frozenset({Kind.WORD, Kind.STRING, Kind.CARTOUCHE})
_KEYWORD_KINDS = frozenset({Kind.WORD, Kind.SYMBOL, Kind.DELIM})


def unquote(token: Token) -> str:
    """The name a WORD, STRING, or CARTOUCHE token denotes."""
    if token.kind is Kind.STRING:
        return token.text[1:-1]
    if token.kind is Kind.CARTOUCHE:
        for opener, closer in (("\\<open>", "\\<close>"), ("‹", "›")):
            if token.text.startswith(opener) and token.text.endswith(closer):
                return token.text[len(opener) : -len(closer)]
    return token.text


def significant(tokens: Iterable[Token]) -> Iterator[Token]:
    """Tokens without layout, (* *) comments, and formal comments."""
    skip_cartouche = False
    for tok in tokens:
        if tok.kind in IGNORABLE:
            continue
        if skip_cartouche and tok.kind is Kind.CARTOUCHE:
            skip_cartouche = False
            continue
        skip_cartouche = tok.kind is Kind.SYMBOL and tok.text in COMMENT_MARKERS
        if not skip_cartouche:
            yield tok


@dataclass(frozen=True)
class Name:
    """A name as written in the source, with the offset of its token."""

    text: str
    start: int


@dataclass(frozen=True)
class KeywordDecl:
    name: str
    kind: CommandKind | None  # None for a minor keyword
    start: int


@dataclass(frozen=True)
class Header:
    name: Name
    imports: tuple[Name, ...]
    keywords: tuple[KeywordDecl, ...]
    begin: int  # offset of the `begin` token, -1 if missing


@dataclass(frozen=True)
class Command:
    """A command: its keyword token and every token up to the last significant
    one before the next command. Layout and comments after that belong to the
    gap before the next command."""

    name: str
    kind: CommandKind
    first: int  # token index of the keyword
    stop: int  # token index after the last token of the command

    def tokens(self, tokens: list[Token]) -> list[Token]:
        return tokens[self.first : self.stop]


@dataclass(frozen=True)
class GoalBlock:
    """A theory-level goal with the proof commands that belong to it.

    ``commands`` indexes into ``Theory.commands``: the statement first.
    ``closed`` is False when the text ends, or a theory-level command starts,
    before the proof finishes.
    """

    statement: int
    stop: int
    closed: bool


@dataclass
class Theory:
    text: str
    tokens: list[Token]
    header: Header | None
    commands: list[Command]
    lines: LineIndex = field(repr=False)

    def command_text(self, command: Command) -> str:
        if command.first == command.stop:
            return ""
        start = self.tokens[command.first].start
        end = self.tokens[command.stop - 1].end
        return self.text[start:end]

    def start(self, command: Command) -> int:
        return self.tokens[command.first].start

    def end(self, command: Command) -> int:
        return self.tokens[command.stop - 1].end

    def goal_blocks(self) -> list[GoalBlock]:
        return list(_goal_blocks(self.commands))


def _parse_keyword_decls(toks: list[Token], i: int) -> tuple[list[KeywordDecl], int]:
    """Parse ``keywords`` declarations starting after the keyword at ``i``."""
    decls: list[KeywordDecl] = []
    pending: list[Token] = []
    n = len(toks)
    while i < n:
        tok = toks[i]
        if tok.kind is Kind.STRING:
            pending.append(tok)
            i += 1
        elif tok.text == "::" and i + 1 < n:
            kind_text = unquote(toks[i + 1])
            kind = CommandKind(kind_text) if kind_text in KIND_NAMES else None
            decls += [KeywordDecl(unquote(t), kind, t.start) for t in pending]
            pending = []
            i += 2
        elif tok.text == "%" and i + 1 < n:
            i += 2  # tag, as in `% "proof"`
        elif tok.text == "(":
            depth = 0
            while i < n:  # file-extension spec of a thy_load command
                depth += {"(": 1, ")": -1}.get(toks[i].text, 0)
                i += 1
                if depth == 0:
                    break
        elif tok.text == "==" and i + 1 < n:
            i += 2  # obsolete alias spec
        elif tok.text == "and":
            decls += [KeywordDecl(unquote(t), None, t.start) for t in pending]
            pending = []
            i += 1
        else:
            break
    decls += [KeywordDecl(unquote(t), None, t.start) for t in pending]
    return decls, i


def parse_header(tokens: Iterable[Token]) -> Header | None:
    """The theory header, from ``theory`` to ``begin``, or None if absent."""
    # Document commands such as `section` may precede the header.
    toks: list[Token] = []
    for tok in significant(tokens):
        if toks or (tok.kind is Kind.WORD and tok.text == "theory"):
            toks.append(tok)
        if toks and tok.kind is Kind.WORD and tok.text == "begin":
            break
    if len(toks) < 2:
        return None
    name = Name(unquote(toks[1]), toks[1].start)
    imports: list[Name] = []
    keywords: list[KeywordDecl] = []
    begin = -1
    i = 2
    section = ""
    while i < len(toks):
        tok = toks[i]
        if tok.kind is Kind.WORD and tok.text in ("imports", "keywords", "abbrevs", "begin"):
            if tok.text == "begin":
                begin = tok.start
                break
            section = tok.text
            i += 1
            if section == "keywords":
                decls, i = _parse_keyword_decls(toks, i)
                keywords += decls
            continue
        if section == "imports" and tok.kind in _NAME_KINDS:
            imports.append(Name(unquote(tok), tok.start))
        i += 1
    return Header(name, tuple(imports), tuple(keywords), begin)


def read_header(path: Path) -> Header | None:
    """Parse only the header of a theory file."""
    return parse_header(iter_tokens(path.read_text(encoding="utf-8")))


def keyword_table(
    headers: Iterable[Header | None], *, builtin: bool = True
) -> dict[str, CommandKind]:
    """Commands declared in ``headers``, on top of the built-in ones unless
    ``builtin`` is False. Later headers win."""
    table = dict(BUILTIN_COMMANDS) if builtin else {}
    for header in headers:
        if header is not None:
            for imp in header.imports:
                table.update(commands_of_import(imp.text))
            for decl in header.keywords:
                if decl.kind is not None:
                    table[decl.name] = decl.kind
    return table


def _keyword_at(
    tokens: list[Token], i: int, table: Mapping[str, CommandKind]
) -> tuple[str, CommandKind | None]:
    """The keyword starting at token ``i``, if any.

    A declared keyword may span a symbolic prefix and a word (``@proof``),
    which the lexer splits in two.
    """
    tok = tokens[i]
    if tok.kind is Kind.SYM_IDENT and i + 1 < len(tokens):
        nxt = tokens[i + 1]
        if nxt.kind is Kind.WORD and (joined := tok.text + nxt.text) in table:
            return joined, table[joined]
    if tok.kind in _KEYWORD_KINDS:
        return tok.text, table.get(tok.text)
    return tok.text, None


def _segment(tokens: list[Token], table: Mapping[str, CommandKind]) -> list[Command]:
    commands: list[Command] = []
    start = -1
    last = -1  # index of the last significant token of the open command
    in_header = False
    prefixed = False
    skip_cartouche = False
    skip_word = False  # second half of a keyword like `@proof`
    for i, tok in enumerate(tokens):
        if tok.kind in IGNORABLE:
            continue
        if skip_word:
            skip_word = False
            last = i
            continue
        if skip_cartouche and tok.kind is Kind.CARTOUCHE:
            skip_cartouche = False
            last = i
            continue
        skip_cartouche = tok.kind is Kind.SYMBOL and tok.text in COMMENT_MARKERS
        name, kind = _keyword_at(tokens, i, table)
        if in_header:
            kind = None  # imports are names, even when they spell a command
            in_header = not (tok.kind is Kind.WORD and tok.text == "begin")
        if kind is CommandKind.QUASI_COMMAND:
            kind = None  # looks like a command, but never starts one
        if kind is not None and not (prefixed and kind is not CommandKind.BEFORE_COMMAND):
            if start >= 0:
                commands.append(_command(tokens, table, start, last + 1))
            start = i
            in_header = kind is CommandKind.THY_BEGIN
        skip_word = kind is not None and name != tok.text
        # `private lemma ...`: the modifier opens the span of the next command.
        prefixed = kind is CommandKind.BEFORE_COMMAND
        last = i
    if start >= 0:
        commands.append(_command(tokens, table, start, last + 1))
    return commands


def _command(
    tokens: list[Token], table: Mapping[str, CommandKind], first: int, stop: int
) -> Command:
    """The command spanning ``tokens[first:stop]``. After ``before_command``
    modifiers (``private lemma``), name and kind are the modified command's."""
    for i in range(first, stop):
        if tokens[i].kind in IGNORABLE:
            continue
        name, kind = _keyword_at(tokens, i, table)
        if kind is not CommandKind.BEFORE_COMMAND:
            if kind is not None:
                return Command(name, kind, first, stop)
            break
    name, kind = _keyword_at(tokens, first, table)
    assert kind is not None
    return Command(name, kind, first, stop)


def _goal_blocks(commands: list[Command]) -> Iterator[GoalBlock]:
    i = 0
    n = len(commands)
    while i < n:
        if commands[i].kind not in THEORY_GOALS:
            i += 1
            continue
        depth = 1
        j = i + 1
        closed = False
        while j < n:
            kind = commands[j].kind
            if kind not in PROOF_KINDS and kind not in (CommandKind.DIAG, *_IN_PROOF):
                break
            if kind in PROOF_GOALS:
                depth += 1
            elif kind in PROOF_TERMINATORS:
                depth -= 1
            elif kind is CommandKind.QED_GLOBAL:
                depth = 0
            j += 1
            if depth == 0:
                closed = True
                break
        yield GoalBlock(i, j, closed)
        i = j


# Theory-level kinds that may also occur inside a proof.
_IN_PROOF = (CommandKind.DOCUMENT_BODY, CommandKind.DOCUMENT_HEADING, CommandKind.DOCUMENT_RAW)


def parse_theory(text: str, table: Mapping[str, CommandKind] | None = None) -> Theory:
    """Tokenize and segment ``text``. Commands declared in its own header are
    added to ``table`` (default: the built-in commands)."""
    tokens = tokenize(text)
    header = parse_header(tokens)
    keywords = dict(table) if table is not None else keyword_table([header])
    for decl in header.keywords if header is not None else ():
        if decl.kind is not None:
            keywords[decl.name] = decl.kind
    return Theory(text, tokens, header, _segment(tokens, keywords), LineIndex(text))
