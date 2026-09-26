"""Per-theory checks: unfinished proofs, lexical errors, document arguments,
and symbol encoding."""

from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.source.keywords import DOCUMENT, CommandKind
from isar_tools.source.lexer import Kind
from isar_tools.source.symbols import TO_ASCII
from isar_tools.source.theory import Theory, goal_name, significant

_UNTERMINATED = {
    "(*": "comment",
    '"': "string",
    "`": "alternative string",
    "{*": "verbatim block",
    "\\<open>": "cartouche",
    "‹": "cartouche",
}
# A text argument: a cartouche, a string, verbatim text, or a single word.
_TEXT_KINDS = frozenset({Kind.CARTOUCHE, Kind.STRING, Kind.VERBATIM, Kind.WORD})


def check_proofs(path: Path, theory: Theory) -> list[Finding]:
    findings: list[Finding] = []
    for command in theory.commands:
        start = theory.start(command)
        if command.name in ("sorry", "\\<proof>"):
            findings.append(
                Finding.at(
                    path,
                    theory.lines,
                    start,
                    "unfinished-proof",
                    f"{command.name} leaves the goal unproved",
                )
            )
        elif command.kind is CommandKind.QED_GLOBAL:
            findings.append(
                Finding.at(path, theory.lines, start, "oops", f"{command.name} abandons the goal")
            )
    for block in theory.goal_blocks():
        if block.closed:
            continue
        statement = theory.commands[block.statement]
        name = goal_name(theory, statement)
        label = f"{statement.name} {name}" if name else statement.name
        where = (
            f"before {theory.commands[block.stop].name}"
            if block.stop < len(theory.commands)
            else "before the end of the file"
        )
        findings.append(
            Finding.at(
                path,
                theory.lines,
                theory.start(statement),
                "unclosed-proof",
                f"the proof of {label} does not end {where}",
            )
        )
    return findings


def check_syntax(path: Path, theory: Theory) -> list[Finding]:
    findings: list[Finding] = []
    for tok in theory.tokens:
        if tok.kind is Kind.ERROR:
            what = next((v for k, v in _UNTERMINATED.items() if tok.text.startswith(k)), "region")
            findings.append(
                Finding.at(path, theory.lines, tok.start, "lexical-error", f"unterminated {what}")
            )
    for command in theory.commands:
        if command.kind not in DOCUMENT:
            continue
        args = list(significant(command.tokens(theory.tokens)))[1:]
        while args and args[0].text == "%" and len(args) > 1:
            args = args[2:]  # document tag, as in `text %invisible`
        if not args or args[0].kind not in _TEXT_KINDS:
            message = (
                f"{command.name} expects a text argument, as in {command.name} \\<open>...\\<close>"
            )
        elif len(args) > 1:
            message = (
                f"unexpected {args[1].text!r} after the text of {command.name}; if it is a "
                "command of another session, include that session's directory with -d"
            )
        else:
            continue
        findings.append(
            Finding.at(path, theory.lines, theory.start(command), "document-argument", message)
        )
    return findings


def check_symbols(path: Path, theory: Theory, *, include_comments: bool = False) -> list[Finding]:
    """Non-ASCII characters, which batch builds can reject where the editor
    accepted them. ``(* *)`` comments are skipped unless ``include_comments``."""
    findings: list[Finding] = []
    for tok in theory.tokens:
        if tok.kind is Kind.COMMENT and not include_comments:
            continue
        for i, ch in enumerate(tok.text):
            if ord(ch) <= 127:
                continue
            ascii_ = TO_ASCII.get(ch)
            hint = f"; write {ascii_}" if ascii_ else "; it has no Isabelle symbol spelling"
            findings.append(
                Finding.at(
                    path,
                    theory.lines,
                    tok.start + i,
                    "non-ascii",
                    f"non-ASCII character {ch!r} (U+{ord(ch):04X}){hint}",
                )
            )
    return findings
