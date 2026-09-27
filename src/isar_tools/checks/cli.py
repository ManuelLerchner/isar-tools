"""``isar check``: project and source hygiene."""

import argparse
import sys
from collections import Counter
from pathlib import Path

from isar_tools.checks.docs import check_docs
from isar_tools.checks.findings import CODES, DEFAULT_GROUPS, GROUPS, Finding
from isar_tools.checks.locales import check_locales
from isar_tools.checks.project import check_project
from isar_tools.checks.theory import check_proofs, check_symbols, check_syntax
from isar_tools.project.workspace import add_include_option, load
from isar_tools.render import RENDERERS, Column, Table, display_path
from isar_tools.style import Style, add_color_option

FORMATS = ("text", "json", "csv")


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:  # pyright: ignore[reportPrivateUsage]
    codes = "\n".join(f"  {code:22} {group:8} {desc}" for code, (group, desc) in CODES.items())
    check = sub.add_parser(
        "check",
        help="Check project and source hygiene",
        description="Check project and source hygiene. Groups: "
        f"{', '.join(GROUPS)}; default: {', '.join(DEFAULT_GROUPS)}.",
        epilog=f"codes:\n{codes}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    check.add_argument(
        "paths", nargs="*", type=Path, default=[Path()], help="project directories or .thy files"
    )
    check.add_argument(
        "--group",
        dest="groups",
        action="append",
        choices=GROUPS,
        help="run this group of checks (repeatable; default: all but symbols, docs, and locales)",
    )
    check.add_argument(
        "--ignore",
        action="append",
        default=[],
        choices=sorted(CODES),
        metavar="CODE",
        help="do not report this code (repeatable)",
    )
    check.add_argument(
        "--include-comments", action="store_true", help="symbols: also check (* *) comments"
    )
    check.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="NAME",
        help="locales: do not report this identifier (repeatable)",
    )
    check.add_argument("--format", choices=FORMATS, default="text")
    add_color_option(check)
    add_include_option(check)
    check.set_defaults(func=run)


def normalize_argv(argv: list[str]) -> list[str]:
    """``check GROUP ...`` means ``check --group GROUP ...``."""
    args = list(argv)
    if len(args) > 1 and args[0] == "check" and args[1] in GROUPS:
        args[1:2] = ["--group", args[1]]
    return args


def collect_findings(args: argparse.Namespace) -> list[Finding]:
    groups: set[str] = set(args.groups or DEFAULT_GROUPS)
    workspace = load(args.paths, args.include)
    findings: list[Finding] = []
    if "project" in groups:
        for project in workspace.projects:
            findings += check_project(project)
    if groups & {"proofs", "syntax", "symbols", "docs"}:
        for source in workspace.sources:
            theory = source.parse()
            if "proofs" in groups:
                findings += check_proofs(source.path, theory)
            if "syntax" in groups:
                findings += check_syntax(source.path, theory)
            if "symbols" in groups:
                findings += check_symbols(
                    source.path, theory, include_comments=args.include_comments
                )
            if "docs" in groups:
                findings += check_docs(source.path, theory)
    if "locales" in groups:
        findings += check_locales(workspace.sources, allow=args.allow)
    ignored = set(args.ignore)
    return sorted({f for f in findings if f.code not in ignored})


def findings_table(findings: list[Finding]) -> Table:
    return Table(
        "findings",
        "Findings",
        [
            Column("path", "path"),
            Column("line", "line", True),
            Column("column", "column", True),
            Column("code", "code"),
            Column("message", "message"),
        ],
        [
            {
                "path": display_path(f.path),
                "line": f.line,
                "column": f.column,
                "code": f.code,
                "message": f.message,
            }
            for f in findings
        ],
    )


# Colour of a finding's code, by group.
_GROUP_COLORS = {
    "project": "magenta",
    "proofs": "yellow",
    "syntax": "red",
    "symbols": "cyan",
    "docs": "green",
    "locales": "blue",
}


def summary(findings: list[Finding]) -> str:
    """``2 findings: 1 missing-theory, 1 unfinished-proof``, most frequent first."""
    if not findings:
        return "no findings"
    counts = Counter(f.code for f in findings)
    parts = ", ".join(
        f"{n} {code}" for code, n in sorted(counts.items(), key=lambda c: (-c[1], c[0]))
    )
    noun = "finding" if len(findings) == 1 else "findings"
    return f"{len(findings)} {noun}: {parts}"


def run(args: argparse.Namespace) -> int:
    findings = collect_findings(args)
    if args.format == "text":
        style = Style.for_stream(args.color, sys.stdout)
        for f in findings:
            where = style(display_path(f.path), "bold") + style(f":{f.line}:{f.column}:", "dim")
            code = style(f.code, _GROUP_COLORS[CODES[f.code][0]], "bold")
            print(f"{where} {code}: {f.message}")
        print(summary(findings), file=sys.stderr)
    else:
        RENDERERS[args.format]([findings_table(findings)], sys.stdout)
    return 1 if findings else 0
