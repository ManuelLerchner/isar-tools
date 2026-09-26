"""Size and shape metrics of one theory, computed from the source model.

Line classes:

- *code*: the line carries a token the prover reads;
- *doc*: otherwise, the line carries a ``(* *)`` comment, a formal comment
  (``\\<comment> \\<open>...\\<close>``), or part of a document command
  (``text``, ``section``, ...);
- *blank*: only layout.

A code line belongs to the command whose first token on that line comes first.
A goal's *statement lines* are the code lines of its statement command; its
*proof lines* are the code lines of the proof commands after it. A one-line
``lemma ... by simp`` has one statement line and no proof lines.
"""

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from isar_tools.source.keywords import DOCUMENT, CommandKind
from isar_tools.source.lexer import LAYOUT, Kind, Token
from isar_tools.source.symbols import symbol_length
from isar_tools.source.theory import COMMENT_MARKERS, Command, Theory, significant, unquote

UNFINISHED = frozenset({"sorry", "oops", "\\<proof>"})


class LineClass(Enum):
    BLANK = "blank"
    CODE = "code"
    DOC = "doc"


@dataclass(frozen=True)
class ProofStats:
    name: str  # "" for an anonymous goal
    command: str
    line: int
    statement_lines: int
    proof_lines: int
    closed: bool
    unfinished: tuple[str, ...]  # sorry, oops, \<proof> in this proof

    @property
    def lines(self) -> int:
        return self.statement_lines + self.proof_lines


@dataclass
class TheoryStats:
    name: str
    lines: int
    code_lines: int
    doc_lines: int
    blank_lines: int
    commands: Counter[str] = field(default_factory=Counter[str])
    kinds: Counter[CommandKind] = field(default_factory=Counter[CommandKind])
    proofs: list[ProofStats] = field(default_factory=list[ProofStats])
    methods: Counter[str] = field(default_factory=Counter[str])
    long_lines: list[int] = field(default_factory=list[int])


def line_count(text: str) -> int:
    """Lines as an editor shows them; a final line break adds no line."""
    return len(text.splitlines())


def _span_lines(theory: Theory, tok: Token) -> range:
    first = theory.lines.line(tok.start)
    last = theory.lines.line(max(tok.start, tok.end - 1))
    return range(first, last + 1)


def classify_lines(theory: Theory) -> dict[int, LineClass]:
    """Class of every line 1..n (n as in ``line_count``)."""
    classes = dict.fromkeys(range(1, line_count(theory.text) + 1), LineClass.BLANK)
    doc_tokens: set[int] = set()
    for command in theory.commands:
        if command.kind in DOCUMENT:
            doc_tokens.update(range(command.first, command.stop))
    formal_comment = False
    for i, tok in enumerate(theory.tokens):
        if tok.kind in LAYOUT:
            continue
        is_marker = tok.kind is Kind.SYMBOL and tok.text in COMMENT_MARKERS
        doc = (
            tok.kind is Kind.COMMENT
            or is_marker
            or (formal_comment and tok.kind is Kind.CARTOUCHE)
            or i in doc_tokens
        )
        formal_comment = is_marker
        for line in _span_lines(theory, tok):
            if not doc:
                classes[line] = LineClass.CODE
            elif classes[line] is LineClass.BLANK:
                classes[line] = LineClass.DOC
    return classes


def _line_owners(theory: Theory, classes: dict[int, LineClass]) -> dict[int, int]:
    """Code line -> index of the command owning it."""
    owners: dict[int, int] = {}
    for index, command in enumerate(theory.commands):
        for tok in significant(command.tokens(theory.tokens)):
            for line in _span_lines(theory, tok):
                if classes.get(line) is LineClass.CODE:
                    owners.setdefault(line, index)
    return owners


def goal_name(theory: Theory, command: Command) -> str:
    """The binding of a goal statement: ``foo`` in ``lemma foo[simp]: ...``."""
    toks = list(significant(command.tokens(theory.tokens)))[1:]
    if toks and toks[0].text == "(":  # target, as in `lemma (in loc) ...`
        depth = 0
        while toks:
            tok = toks.pop(0)
            depth += {"(": 1, ")": -1}.get(tok.text, 0)
            if depth == 0:
                break
    if len(toks) >= 2 and toks[0].kind in (Kind.WORD, Kind.STRING) and toks[1].text in (":", "["):
        return unquote(toks[0])
    return ""


def theory_stats(
    theory: Theory, *, max_line_length: int = 100, methods: frozenset[str] = frozenset()
) -> TheoryStats:
    classes = classify_lines(theory)
    counts = Counter(classes.values())
    stats = TheoryStats(
        name=theory.header.name.text if theory.header is not None else "",
        lines=len(classes),
        code_lines=counts[LineClass.CODE],
        doc_lines=counts[LineClass.DOC],
        blank_lines=counts[LineClass.BLANK],
    )
    for command in theory.commands:
        stats.commands[command.name] += 1
        stats.kinds[command.kind] += 1
        if command.kind not in DOCUMENT:
            for tok in command.tokens(theory.tokens):
                if tok.kind is Kind.WORD and tok.text in methods:
                    stats.methods[tok.text] += 1
    for number, line in enumerate(theory.text.splitlines(), start=1):
        if symbol_length(line) > max_line_length:
            stats.long_lines.append(number)

    owners = _line_owners(theory, classes)
    lines_of: Counter[int] = Counter(owners.values())
    for block in theory.goal_blocks():
        statement = theory.commands[block.statement]
        proof = range(block.statement + 1, block.stop)
        stats.proofs.append(
            ProofStats(
                name=goal_name(theory, statement),
                command=statement.name,
                line=theory.lines.line(theory.start(statement)),
                statement_lines=lines_of[block.statement],
                proof_lines=sum(lines_of[i] for i in proof),
                closed=block.closed,
                unfinished=tuple(
                    theory.commands[i].name for i in proof if theory.commands[i].name in UNFINISHED
                ),
            )
        )
    return stats
