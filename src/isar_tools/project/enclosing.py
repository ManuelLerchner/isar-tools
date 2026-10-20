"""What encloses a line of a theory: the declaration, and the goals, cases,
and ``{ }`` blocks of its proof."""

from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.project.names import entities
from isar_tools.source.keywords import PROOF_GOALS, PROOF_TERMINATORS, THEORY_GOALS, CommandKind
from isar_tools.source.theory import Theory, goal_name

# The text of a span is cut to this many characters.
_WIDTH = 60


@dataclass(frozen=True)
class Span:
    command: str  # the keyword that opens it
    text: str  # a name, or the start of what follows the keyword
    start: int  # text offset
    end: int  # text offset after its last token


@dataclass
class _Frame:
    """An open goal or ``{ }`` block, and the ``case`` open in it."""

    command: int  # index into Theory.commands
    case: int | None = None
    spans: list[Span] = field(default_factory=list[Span])


def _text(theory: Theory, index: int) -> str:
    command = theory.commands[index]
    if name := goal_name(theory, command):
        return name
    rest = theory.command_text(command).removeprefix(command.name)
    text = " ".join(rest.split())
    return text if len(text) <= _WIDTH else text[: _WIDTH - 3] + "..."


def _span(theory: Theory, first: int, last: int) -> Span:
    """The span from command ``first`` to command ``last``, both included."""
    commands = theory.commands
    name = commands[first].name
    return Span(
        name, _text(theory, first), theory.start(commands[first]), theory.end(commands[last])
    )


def proof_spans(theory: Theory, statement: int, stop: int) -> list[Span]:
    """The goals, cases, and blocks of the proof of the theory-level goal
    ``commands[statement]``, whose proof ends before ``commands[stop]``."""
    spans: list[Span] = []
    stack = [_Frame(statement)]

    def close_case(frame: _Frame, last: int) -> None:
        if frame.case is not None:
            spans.append(_span(theory, frame.case, last))
            frame.case = None

    def close(last: int, case_last: int) -> None:
        frame = stack.pop()
        close_case(frame, case_last)
        if frame.command != statement:
            spans.append(_span(theory, frame.command, last))

    for i in range(statement + 1, stop):
        command = theory.commands[i]
        if command.kind in PROOF_GOALS or command.kind is CommandKind.PRF_OPEN:
            stack.append(_Frame(i))
        elif command.kind in PROOF_TERMINATORS or command.kind is CommandKind.PRF_CLOSE:
            close(i, i - 1)
        elif command.kind is CommandKind.QED_GLOBAL:
            while stack:
                close(i, i - 1)
        elif command.kind is CommandKind.NEXT_BLOCK:
            close_case(stack[-1], i - 1)
        elif command.name == "case":
            close_case(stack[-1], i - 1)
            stack[-1].case = i
        if not stack:
            break
    while stack:  # an unfinished proof
        close(stop - 1, stop - 1)
    return sorted(spans, key=lambda s: (s.start, -s.end))


def enclosing(theory: Theory, path: Path, line: int) -> list[Span]:
    """The declarations whose extent holds ``line`` (1-based), then the spans
    of their proof that hold it, outermost first; empty outside every
    declaration."""
    name = theory.header.name.text if theory.header else path.stem
    lines = theory.lines

    def holds(start: int, end: int) -> bool:
        return lines.line(start) <= line <= lines.line(max(start, end - 1))

    owners = [
        e
        for e in entities(theory, name, path)
        if not e.member and not e.derived_from and holds(e.start, e.end)
    ]
    if not owners:
        return []
    spans = [Span(e.command, e.qualified, e.start, e.end) for e in owners]
    index = owners[0].command_index
    if theory.commands[index].kind in THEORY_GOALS:
        stop = next(b.stop for b in theory.goal_blocks() if b.statement == index)
        spans += [s for s in proof_spans(theory, index, stop) if holds(s.start, s.end)]
    return spans
