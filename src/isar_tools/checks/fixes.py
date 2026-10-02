"""``isar check --fix``: apply the fixes findings carry.

``safe`` applies the fixes that keep a theory's meaning, ``unsafe-only`` the
others, ``all`` both. Fixes are lexical, like the checks: a theory should build
after an unsafe fix, but only a build can tell. A fix whose edits overlap one
already taken waits for the next round, which re-checks the edited files.
"""

from collections.abc import Iterable
from pathlib import Path

from isar_tools.checks.findings import Edit, Finding, Fix
from isar_tools.source.files import read_source, write_source

MODES = ("safe", "unsafe-only", "all")


def wanted(fix: Fix | None, mode: str) -> bool:
    if fix is None:
        return False
    return mode == "all" or fix.safe == (mode == "safe")


def _overlap(a: Edit, b: Edit) -> bool:
    return (a.start < b.end and b.start < a.end) or a.start == b.start


def apply_fixes(findings: Iterable[Finding], mode: str) -> int:
    """Apply the wanted fixes of ``findings``; how many were applied."""
    by_path: dict[Path, list[Fix]] = {}
    for f in findings:
        fixes = by_path.setdefault(f.path, [])
        if f.fix is not None and wanted(f.fix, mode) and f.fix not in fixes:
            fixes.append(f.fix)
    applied = 0
    for path, fixes in by_path.items():
        if not fixes:
            continue
        taken: list[Edit] = []
        for fix in fixes:
            if any(_overlap(e, t) for e in fix.edits for t in taken):
                continue
            taken += fix.edits
            applied += 1
        text = read_source(path)
        for e in sorted(taken, key=lambda e: e.start, reverse=True):
            text = text[: e.start] + e.text + text[e.end :]
        write_source(path, text)
    return applied
