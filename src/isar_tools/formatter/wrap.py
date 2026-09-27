"""Wrapping long lines.

A line longer than the limit (in Isabelle symbols: ``\\<Longrightarrow>``
counts as one) is broken at a space between two tokens. Outer syntax treats a
line break like a space, and strings, cartouches, and comments are single
tokens, so a break can never change what the prover reads. The pieces are then
indented by the formatter.

Where to break, in order of preference:

1. before a command later on the line (``using``, ``by``, ...), so
   ``have "..." using a by simp`` becomes one command per line, indented by
   proof structure;
2. at the shallowest bracket depth, at the rightmost space that makes the
   first part fit.

There is never a break between a command keyword and its first argument, and
a break must shorten the line; a line that cannot be shortened (one long
string, say) is left as it is. Other pieces go one indent step deeper than
the line they came from. Wrapping repeats until no line changes.
"""

from collections.abc import Mapping

from isar_tools.formatter.formatter import (
    Options,
    SourceLine,
    format_theory,
    line_width,
    source_lines,
    token_depths,
)
from isar_tools.source.keywords import CommandKind
from isar_tools.source.lexer import Kind
from isar_tools.source.theory import Theory, parse_theory


def _break(
    line: SourceLine, starts: set[int], depths: list[int], limit: int, step: int, newline: str
) -> tuple[int, str] | None:
    """Where to break one line: (index of a SPACE token, its replacement)."""
    content = line.content
    if not content or line.frozen:
        return None
    indent = line_width(line.indent)
    width = line_width(line.indent + "".join(t.text for t in content))
    if width <= limit:
        return None
    rest_indent = indent + step
    offset = line.first + line.tokens.index(content[0])
    # (index of the SPACE token, width of the text before it, next token index).
    # Inside a line a SPACE always sits between two other tokens.
    spaces: list[tuple[int, int, int]] = []
    used = indent
    for k, tok in enumerate(content):
        after_keyword = offset + k - 1 in starts
        shortens = rest_indent + (width - used - 1) < width
        if tok.kind is Kind.SPACE and not after_keyword and indent < used and shortens:
            spaces.append((offset + k, used, offset + k + 1))
        used += line_width(tok.text)
    if not spaces:
        return None
    commands = [sp for sp in spaces if sp[2] in starts]
    if commands:
        fitting = [sp for sp in commands if sp[1] <= limit]
        # No indentation: the formatter indents the command by structure.
        return (fitting[-1] if fitting else commands[0])[0], newline
    shallowest = min(depths[sp[2]] for sp in spaces)
    level = [sp for sp in spaces if depths[sp[2]] == shallowest]
    fitting = [sp for sp in level if sp[1] <= limit]
    return (fitting[-1] if fitting else level[0])[0], newline + " " * rest_indent


def _breaks(theory: Theory, limit: int, step: int) -> dict[int, str]:
    """Token index of a SPACE to replace -> its replacement, one per long line."""
    newline = next((t.text for t in theory.tokens if t.kind is Kind.NEWLINE), "\n")
    starts = {c.first for c in theory.commands}
    depths = token_depths(theory)
    edits: dict[int, str] = {}
    for line in source_lines(theory):
        found = _break(line, starts, depths, limit, step, newline)
        if found is not None:
            edits[found[0]] = found[1]
    return edits


def format_source(
    text: str, table: Mapping[str, CommandKind] | None = None, options: Options | None = None
) -> str:
    """Format ``text``, and wrap long lines if ``options.max_line_length`` is set.

    Wrapping terminates: every round splits at least one line into two
    non-empty lines, and a text has no more lines than tokens.
    """
    options = options if options is not None else Options()
    text = format_theory(parse_theory(text, table), options)
    if options.max_line_length is None:
        return text
    while edits := _breaks(parse_theory(text, table), options.max_line_length, options.indent):
        theory = parse_theory(text, table)
        text = "".join(edits.get(i, t.text) for i, t in enumerate(theory.tokens))
        text = format_theory(parse_theory(text, table), options)
    return text
