"""Source-file checks: theory names, encoding, hygiene, and debugging leftovers.

- ``theory-name`` (syntax): the header names a theory other than the file, or a
  qualified one; Isabelle refuses to load it ("Bad theory name").
- ``invalid-utf8`` (syntax): Isabelle reads theories as UTF-8 only.
- ``hygiene`` group, after Isabelle's ``check_sources``: tab and carriage
  return characters, bidirectional Unicode controls (which make text display
  in an order other than the one the prover reads), and file names Windows
  cannot check out.
- ``leftovers`` group, after isabelle-linter's ``proof_finder``,
  ``counter_example_finder``, and ``diagnostic_command``: commands that search
  or print but prove nothing, left in from an interactive session, and
  ``defer``, ``prefer``, and ``back``, which tie a proof to the order in which
  goals and results come.
"""

import re
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.source.keywords import CommandKind
from isar_tools.source.lexer import LineIndex
from isar_tools.source.theory import Theory, significant

PROOF_SEARCH = frozenset({"sledgehammer", "try", "try0", "solve_direct"})
GOAL_REORDERING = frozenset({"defer", "prefer"})
COUNTEREXAMPLE_SEARCH = frozenset({"nitpick", "quickcheck", "refute"})
# Diagnostic commands that are not kind `diag` in every table.
DIAGNOSTIC = frozenset({"ML_val"})

# U+202A..U+202E (embeddings, overrides) and U+2066..U+2069 (isolates).
_BIDI = re.compile("[‪-‮⁦-⁩]")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_WINDOWS_FORBIDDEN = re.compile(r'[<>:"|?*\\]')


def check_theory_name(path: Path, theory: Theory) -> list[Finding]:
    header = theory.header
    if header is None:
        return []
    name = header.name.text.strip('"')
    if "." in name:
        message = f"theory name {name} is qualified; the header names the file's own theory"
    elif name != path.stem:
        message = f"theory {name} in file {path.name}; Isabelle expects theory {path.stem}"
    else:
        return []
    return [Finding.at(path, theory.lines, header.name.start, "theory-name", message)]


def invalid_utf8(path: Path, data: bytes, error: UnicodeDecodeError) -> Finding:
    line = data.count(b"\n", 0, error.start) + 1
    column = error.start - (data.rfind(b"\n", 0, error.start) + 1) + 1
    return Finding(path, line, column, "invalid-utf8", f"not UTF-8: byte 0x{data[error.start]:02x}")


def check_hygiene(path: Path, text: str) -> list[Finding]:
    lines = LineIndex(text)
    findings: list[Finding] = []
    # One finding per line is enough to find them.
    for number, line in enumerate(text.split("\n"), start=1):
        tab = line.find("\t")
        if tab >= 0:
            findings.append(Finding(path, number, tab + 1, "tab", "tab character"))
    cr = text.find("\r")
    if cr >= 0:
        what = "CRLF line endings" if text[cr : cr + 2] == "\r\n" else "carriage return"
        findings.append(Finding.at(path, lines, cr, "carriage-return", f"{what} (first here)"))
    for m in _BIDI.finditer(text):
        char = f"U+{ord(m.group()):04X}"
        findings.append(
            Finding.at(path, lines, m.start(), "bidi-control", f"bidirectional control {char}")
        )
    stem = path.name.split(".", 1)[0].lower()
    if stem in _WINDOWS_RESERVED or _WINDOWS_FORBIDDEN.search(path.name):
        message = f"{path.name} cannot be checked out on Windows"
        findings.append(Finding(path, 1, 1, "reserved-file-name", message))
    return findings


def check_leftovers(path: Path, theory: Theory) -> list[Finding]:
    findings: list[Finding] = []
    for command in theory.commands:
        name = command.name
        if name in PROOF_SEARCH:
            code, message = "proof-search", f"{name} searches for a proof; replace it by the proof"
        elif name in COUNTEREXAMPLE_SEARCH:
            words = {t.text for t in significant(command.tokens(theory.tokens))}
            if "expect" in words:
                continue  # `nitpick [expect = none]` documents and checks a result
            code, message = (
                "counterexample-search",
                f"{name} without expect: its outcome is not checked",
            )
        elif name in GOAL_REORDERING:
            code, message = "goal-reordering", f"{name} reorders the goals; prove them in order"
        elif name == "back":
            code, message = (
                "backtracking",
                "back takes the next result of the previous method, which can change with it",
            )
        elif command.kind is CommandKind.DIAG or name in DIAGNOSTIC:
            code, message = "diagnostic-command", f"{name} prints but proves nothing"
        else:
            continue
        findings.append(Finding.at(path, theory.lines, theory.start(command), code, message))
    return findings
