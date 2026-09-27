"""Documentation coverage: the opt-in ``docs`` group.

A style policy, ported from Voblint's ``extract_definitions.py --lint``:
theories, headings, and locales and classes carry prose, routine
declarations need not. All rules are stated over the command sequence of
:class:`~isar_tools.source.theory.Theory`:

- A *text block* is a ``text`` (or ``txt``) command, with any argument form
  and document tag. ``text_raw`` is raw LaTeX, not prose, and does not count.
  Neither do ``(* *)`` comments, which are not part of the document, nor
  formal comments ``\\<comment> \\<open>...\\<close>``, which annotate one
  term or proof step and belong to the command they occur in.
- ``undocumented-theory``: no text block before the first command that is
  none of: the ``theory`` header, a document command (heading, text,
  ``text_raw``), or a preamble command that only opens a context or adjusts
  syntax and name visibility (``context``, ``unbundle``, ``declare``,
  ``hide_const``, ``notation``, ...; see ``_PREAMBLE``). Text before the
  header counts.
- ``undocumented-heading``: a heading (``chapter`` ... ``subparagraph``)
  whose next command is not a text block and whose previous command is not a
  text block either. For a heading right before the ``theory`` header, the
  next command is the first one after the header.
- ``undocumented-locale`` / ``undocumented-class``: a ``locale`` or ``class``
  declaration whose previous command is not a text block.

"Next" and "previous" mean adjacent in the command sequence: blank lines and
comments in between do not matter, any other command does.
"""

from itertools import dropwhile
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.source.keywords import DOCUMENT, CommandKind
from isar_tools.source.theory import Command, Theory, significant, unquote

# Commands that may precede a theory's opening text: they open a context or
# adjust syntax and name visibility, but declare nothing.
_PREAMBLE = frozenset(
    {
        "context",
        "unbundle",
        "declare",
        "hide_class",
        "hide_type",
        "hide_const",
        "hide_fact",
        "notation",
        "no_notation",
        "type_notation",
        "no_type_notation",
        "no_syntax",
        "no_translations",
    }
)
_SKIPPED = DOCUMENT | {CommandKind.THY_BEGIN}
# Declarations that must be preceded by a text block, with their finding code.
_DECLARATIONS = {"locale": "undocumented-locale", "class": "undocumented-class"}


def _is_text(command: Command | None) -> bool:
    return command is not None and command.kind is CommandKind.DOCUMENT_BODY


def _argument(theory: Theory, command: Command) -> str:
    """The first argument of ``command``, after modifiers (``private``) and
    document tags, on one line."""
    tokens = significant(command.tokens(theory.tokens))
    args = list(dropwhile(lambda t: t.text != command.name, tokens))[1:]
    while len(args) > 1 and args[0].text == "%":
        args = args[2:]
    return " ".join(unquote(args[0]).split()) if args else ""


def check_docs(path: Path, theory: Theory) -> list[Finding]:
    commands = theory.commands
    findings: list[Finding] = []

    def report(command: Command, code: str, message: str) -> None:
        findings.append(Finding.at(path, theory.lines, theory.start(command), code, message))

    header = next((c for c in commands if c.kind is CommandKind.THY_BEGIN), None)
    if header is not None:
        opening = (
            c for c in commands if _is_text(c) or not (c.kind in _SKIPPED or c.name in _PREAMBLE)
        )
        first = next(opening, None)
        if not _is_text(first):
            report(
                header,
                "undocumented-theory",
                "theory has no text block before its first declaration",
            )
    for i, command in enumerate(commands):
        previous = commands[i - 1] if i > 0 else None
        if command.kind is CommandKind.DOCUMENT_HEADING:
            j = i + 1
            if j < len(commands) and commands[j].kind is CommandKind.THY_BEGIN:
                j += 1
            following = commands[j] if j < len(commands) else None
            if not _is_text(following) and not _is_text(previous):
                title = _argument(theory, command)
                report(
                    command,
                    "undocumented-heading",
                    f"{command.name} {title!r} has no text block next to it",
                )
        elif command.name in _DECLARATIONS and not _is_text(previous):
            report(
                command,
                _DECLARATIONS[command.name],
                f"{command.name} {_argument(theory, command)} is not preceded by a text block",
            )
    return findings
