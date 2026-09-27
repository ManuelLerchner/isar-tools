"""Conservative formatter for Isabelle theory files.

Guarantees, by construction:

- Only layout changes: leading whitespace of a line, trailing whitespace, and
  runs of blank lines. No token is changed, added, or removed, and the
  whitespace between two tokens on a line is never touched, so tokens cannot
  merge and the prover reads the same token sequence.
- Comments, strings, cartouches (document text, ML, ...), and verbatim blocks
  are never rewritten. A line that starts a token spanning several lines keeps
  its indentation, so the token's continuation lines stay aligned with it.
- Idempotence: formatting formatted text changes nothing.

Indentation follows proof structure:

- theory-level commands at column 0;
- ``proof``, ``next``, and ``qed`` aligned with the goal they prove;
- commands inside a proof block, and inside ``{ ... }``, one step deeper;
- commands that refine a pending goal (``using``, ``apply``, ``by``,
  ``done``, ...) one step deeper than the goal statement;
- a line starting with ``using``/``unfolding``/... whose ``proof`` follows on
  the same line aligned like that ``proof``;
- statement clauses (``fixes``, ``assumes``, ``shows``, ``for``, ...) outside
  brackets one step deeper than their command; ``and`` deeper than its
  clause (one step, unless it already is deeper);
- other continuation lines keep their offset relative to the command's first
  line.

By default the formatter only raises lines indented less than their structure
requires and keeps deeper indentation, so projects with a different indent
width or alignment style see few changes. ``Options.normalize`` sets every
structural line exactly.

Two kinds of existing indentation carry information the formatter cannot
recompute, and are kept in either mode:

- theory-level commands nested in a ``begin ... end`` block (``context``,
  ``instantiation``, ...), whose indentation is a project's choice;
- apply scripts, whose indentation often encodes the number of open subgoals;
  their lines are only ever indented further, never less.

Lines that start with a comment keep their indentation. ``where`` is not
treated as a clause: projects place it in too many ways.
"""

import re
from dataclasses import dataclass, field
from enum import Enum

from isar_tools.source.keywords import (
    DOCUMENT,
    PROOF_GOALS,
    PROOF_KINDS,
    THEORY_GOALS,
    CommandKind,
)
from isar_tools.source.lexer import Kind, Token
from isar_tools.source.symbols import symbol_length
from isar_tools.source.theory import COMMENT_MARKERS, Theory

K = CommandKind
_NEWLINE = re.compile(r"\r\n|\r|\n")

# Continuation lines starting with one of these words are statement clauses.
CLAUSES = frozenset(
    {
        "fixes",
        "assumes",
        "shows",
        "obtains",
        "defines",
        "includes",
        "notes",
        "constrains",
        "rewrites",
        "for",
        "if",
        "when",
        "imports",
        "keywords",
        "abbrevs",
    }
)


@dataclass(frozen=True)
class Options:
    indent: int = 2
    max_blank_lines: int = 2
    # False: only raise lines indented less than their structure requires, and
    # keep deeper indentation. True: set every structural line exactly.
    normalize: bool = False
    # Wrap lines longer than this many Isabelle symbols (see wrap.py); None: off.
    max_line_length: int | None = None


class FormatError(Exception):
    """The text cannot be formatted safely."""


class _Frame(Enum):
    GOAL = "goal"  # a pending goal; refinements go one step deeper
    BLOCK = "block"  # proof ... qed; contents one step deeper
    BRACE = "brace"  # { ... }
    NOTEPAD = "notepad"  # notepad begin ... end


@dataclass
class SourceLine:
    """Tokens between two NEWLINE tokens. A token spanning several physical
    lines (a multi-line string, say) stays inside one such line."""

    tokens: list[Token]
    newline: str  # the NEWLINE token ending the line, "" at end of text
    first: int  # index into the theory's tokens of the first token

    @property
    def indent(self) -> str:
        return self.tokens[0].text if self.tokens and self.tokens[0].kind is Kind.SPACE else ""

    @property
    def content(self) -> list[Token]:
        """Tokens without leading and trailing whitespace."""
        toks = self.tokens
        start = 1 if toks and toks[0].kind is Kind.SPACE else 0
        stop = len(toks) - 1 if len(toks) > start and toks[-1].kind is Kind.SPACE else len(toks)
        return toks[start:stop]

    @property
    def frozen(self) -> bool:
        """Starts a token that continues on later lines: re-indenting this
        line would misalign the token's continuation lines."""
        return any("\n" in t.text or "\r" in t.text for t in self.content)


def source_lines(theory: Theory) -> list[SourceLine]:
    lines: list[SourceLine] = []
    current: list[Token] = []
    first = 0
    for i, tok in enumerate(theory.tokens):
        if tok.kind is Kind.NEWLINE:
            lines.append(SourceLine(current, tok.text, first))
            current = []
            first = i + 1
        else:
            current.append(tok)
    lines.append(SourceLine(current, "", first))
    return lines


@dataclass
class _Command:
    base: int  # new indent of the line the command starts on
    delta: int  # new minus old indent of that line
    clause: int | None = None  # indent of the latest clause line, if any


# Commands that refine the pending goal without closing it.
_REFINEMENTS = frozenset({K.PRF_DECL, K.PRF_CHAIN})
# Commands of an apply script. Their indentation may encode the number of open
# subgoals, which only the prover knows, so it is never reduced.
_SCRIPT = frozenset({K.PRF_SCRIPT, K.QED_SCRIPT, K.PRF_SCRIPT_GOAL})


@dataclass
class _State:
    options: Options
    frames: list[tuple[_Frame, int]] = field(default_factory=list[tuple[_Frame, int]])
    # Frame depth of each goal refined by an apply script -> the shift applied
    # to the script's first line; later script lines keep their offsets.
    scripted: dict[int, int] = field(default_factory=dict[int, int])
    blocks: int = 0  # depth of `begin ... end` blocks below the theory

    def content(self) -> int:
        if not self.frames:
            return 0
        return self.frames[-1][1] + self.options.indent

    def indent(self, kind: CommandKind, old: int, proof_follows: bool) -> int:
        """Indent of a line whose first command has ``kind``, before the
        command updates the state. ``old`` is the line's current indent;
        ``proof_follows`` says that `proof` starts later on the same line."""
        frames = self.frames
        top = frames[-1] if frames else None
        in_proof = kind in PROOF_KINDS or (frames and kind in (*DOCUMENT, K.DIAG))
        if not in_proof:
            depth = self.blocks - 1 if kind is K.THY_END and self.blocks else self.blocks
            return old if depth else 0  # nested in a begin ... end block: keep
        goal = top is not None and top[0] is _Frame.GOAL
        if (
            goal
            and top is not None
            and (kind is K.PRF_BLOCK or (proof_follows and kind in _REFINEMENTS))
        ):
            return top[1]
        if kind is K.NEXT_BLOCK and top is not None and top[0] is _Frame.BLOCK:
            return top[1]
        if kind is K.QED_BLOCK:
            block = self._innermost(_Frame.BLOCK)
            return block if block is not None else self.content()
        if kind is K.PRF_CLOSE:
            brace = self._innermost(_Frame.BRACE)
            return brace if brace is not None else self.content()
        if kind is K.QED_GLOBAL and frames:
            return max(old, frames[0][1] + self.options.indent)
        if goal and len(frames) in self.scripted:
            return max(old + self.scripted[len(frames)], self.content())
        if goal and kind in _SCRIPT:
            return max(old, self.content())
        return self.content()

    def _innermost(self, frame: _Frame) -> int | None:
        for kind, indent in reversed(self.frames):
            if kind is frame:
                return indent
        return None

    def update(
        self, name: str, kind: CommandKind, line_indent: int, delta: int, opens_block: bool
    ) -> None:
        """Apply a command to the state. ``delta`` is how far its line moved."""
        if kind in _SCRIPT and self.frames and len(self.frames) not in self.scripted:
            self.scripted[len(self.frames)] = delta
        frames = self.frames
        top = frames[-1] if frames else None
        if kind in THEORY_GOALS:
            frames[:] = [(_Frame.GOAL, line_indent)]
        elif name == "notepad":
            frames[:] = [(_Frame.NOTEPAD, line_indent)]
        elif kind not in PROOF_KINDS and kind not in (*DOCUMENT, K.DIAG):
            frames.clear()  # a theory-level command ends any open proof
        elif kind is K.PRF_BLOCK and top is not None and top[0] is _Frame.GOAL:
            frames[-1] = (_Frame.BLOCK, top[1])
        elif kind is K.PRF_BLOCK:
            frames.append((_Frame.BLOCK, line_indent))
        elif kind in PROOF_GOALS:
            frames.append((_Frame.GOAL, line_indent))
        elif kind is K.PRF_OPEN:
            frames.append((_Frame.BRACE, line_indent))
        elif kind in (K.QED, K.QED_SCRIPT) and top is not None and top[0] is _Frame.GOAL:
            frames.pop()
        elif kind is K.QED_BLOCK:
            self._pop_to(_Frame.BLOCK)
        elif kind is K.PRF_CLOSE:
            self._pop_to(_Frame.BRACE)
        elif kind is K.QED_GLOBAL:
            frames.clear()
        self.scripted = {d: v for d, v in self.scripted.items() if d <= len(frames)}
        if opens_block:
            self.blocks += 1
        elif kind is K.THY_END and self.blocks:
            self.blocks -= 1

    def _pop_to(self, frame: _Frame) -> None:
        while self.frames:
            kind, _ = self.frames.pop()
            if kind is frame:
                return


def line_width(text: str) -> int:
    """Display width in Isabelle symbols, tabs expanded to 8 columns."""
    return symbol_length(text.expandtabs(8))


def token_depths(theory: Theory) -> list[int]:
    """Bracket depth before each token, counted within its command."""
    depths = [0] * len(theory.tokens)
    starts = {c.first for c in theory.commands}
    depth = 0
    for i, tok in enumerate(theory.tokens):
        if i in starts:
            depth = 0
        depths[i] = depth
        if tok.kind is Kind.DELIM and tok.text in ("(", "["):
            depth += 1
        elif tok.kind is Kind.DELIM and tok.text in (")", "]") and depth:
            depth -= 1
    return depths


def _opens_block(theory: Theory, first: int, stop: int, depths: list[int]) -> bool:
    """Whether a command's own tokens include `begin`, as in `context begin`."""
    return any(
        tok.kind is Kind.WORD and tok.text == "begin" and depths[first + i] == 0
        for i, tok in enumerate(theory.tokens[first:stop])
    )


def format_theory(theory: Theory, options: Options | None = None) -> str:
    """The formatted text of ``theory``.

    Raises ``FormatError`` if the text has an unterminated comment, string,
    cartouche, or verbatim block, since its extent is then unknown.
    """
    options = options if options is not None else Options()
    for tok in theory.tokens:
        if tok.kind is Kind.ERROR:
            line = theory.lines.line(tok.start)
            raise FormatError(f"line {line}: unterminated comment, string, or cartouche")

    starts = {c.first: (index, c) for index, c in enumerate(theory.commands)}
    owner: dict[int, int] = {}  # token index -> index of the command containing it
    for index, command in enumerate(theory.commands):
        for i in range(command.first, command.stop):
            owner[i] = index
    depths = token_depths(theory)
    state = _State(options)
    commands: dict[int, _Command] = {}
    out: list[str] = []
    blank_run = 0
    started = False

    for line in source_lines(theory):
        content = line.content
        if not content:
            blank_run += 1
            if started and blank_run <= options.max_blank_lines:
                out.append(line.newline)
            continue
        blank_run = 0
        started = True
        first_index = line.first + line.tokens.index(content[0])
        line_starts = [
            starts[i] for i in range(first_index, line.first + len(line.tokens)) if i in starts
        ]
        old = line_width(line.indent)
        head = content[0]
        new = old
        if first_index in starts:
            _, command = starts[first_index]
            proof_follows = any(c.kind is K.PRF_BLOCK for _, c in line_starts[1:])
            new = state.indent(command.kind, old, proof_follows)
        elif (
            first_index in owner
            and depths[first_index] == 0
            and head.kind is Kind.WORD
            and head.text in (*CLAUSES, "and", "begin")
        ):
            info = commands[owner[first_index]]
            if head.text == "and":
                # Deeper than its clause; an existing deeper alignment (such as
                # `and` right-aligned under `assumes`) is kept.
                clause = info.clause if info.clause is not None else info.base
                new = old if old > clause else clause + options.indent
            elif head.text == "begin":
                new = info.base
            else:
                new = info.base + options.indent
                info.clause = new
        elif first_index in owner and not _is_comment(head):
            new = max(0, old + commands[owner[first_index]].delta)
        if not options.normalize:
            new = max(new, old)
        if line.frozen:
            new = old
        indent = line.indent if new == old else " " * new
        out.append(indent + "".join(t.text for t in content) + line.newline)

        # Commands starting on this line update the proof state in order.
        for index, command in line_starts:
            commands[index] = _Command(new, new - old)
            opens = command.kind is K.THY_DECL_BLOCK and _opens_block(
                theory, command.first, command.stop, depths
            )
            state.update(command.name, command.kind, new, new - old, opens)

    # Exactly one line break at the end of a non-empty text, in the style of
    # the first line break that remains, so a second run picks the same one.
    text = "".join(out).rstrip("\r\n")
    kept = _NEWLINE.search(text)
    first = next((t.text for t in theory.tokens if t.kind is Kind.NEWLINE), "\n")
    return text + (kept.group(0) if kept else first) if text else ""


def _is_comment(tok: Token) -> bool:
    return tok.kind is Kind.COMMENT or (tok.kind is Kind.SYMBOL and tok.text in COMMENT_MARKERS)
