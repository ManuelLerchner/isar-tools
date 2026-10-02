"""``isar check``: project and source hygiene."""

import argparse
import sys
from collections import Counter
from pathlib import Path

from isar_tools.checks.docs import check_docs
from isar_tools.checks.findings import CODES, DEFAULT_GROUPS, GROUPS, Finding, unsuppressed
from isar_tools.checks.links import LINK_SUFFIXES, check_links
from isar_tools.checks.locales import check_locales
from isar_tools.checks.methods import check_methods
from isar_tools.checks.notation import check_notation
from isar_tools.checks.project import check_project
from isar_tools.checks.prose import check_prose
from isar_tools.checks.redundant import check_redundant
from isar_tools.checks.retired import check_retired, read_retired
from isar_tools.checks.sources import (
    check_hygiene,
    check_leftovers,
    check_theory_name,
    invalid_utf8,
)
from isar_tools.checks.theory import check_proofs, check_symbols, check_syntax
from isar_tools.checks.unused import check_unused
from isar_tools.config import add_exclude_option
from isar_tools.project.model import Project
from isar_tools.project.workspace import InputError, SourceFile, add_include_option, load
from isar_tools.render import RENDERERS, Column, Table, display_path
from isar_tools.source.theory import Theory
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
        "paths",
        nargs="*",
        type=Path,
        default=[Path()],
        help="project directories or .thy files; for links, also .html and .md files",
    )
    check.add_argument(
        "--group",
        dest="groups",
        action="append",
        choices=GROUPS,
        help=f"run this group of checks (repeatable; default: {', '.join(DEFAULT_GROUPS)})",
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
        help="locales, notation, prose, unused: do not report this identifier (repeatable)",
    )
    check.add_argument(
        "--leaf-session",
        action="append",
        default=[],
        metavar="SESSION",
        help="unused: the lemmas of this session are results; do not report them "
        "(repeatable; adds to check.leaf-sessions)",
    )
    check.add_argument(
        "--retired",
        action="append",
        default=[],
        metavar="NAME",
        help="retired: report this identifier (repeatable; adds to check.retired)",
    )
    check.add_argument(
        "--retired-file",
        action="append",
        default=[],
        type=Path,
        metavar="FILE",
        help="retired: report the identifiers listed in FILE, one per line, # comments "
        "(repeatable; adds to check.retired-file)",
    )
    check.add_argument(
        "--browser-info",
        type=Path,
        metavar="DIR",
        help="links: check against this built HTML presentation (Isabelle's browser_info)",
    )
    check.add_argument(
        "--link-base",
        action="append",
        default=[],
        metavar="URL",
        help="links: a link below URL points into --browser-info (repeatable)",
    )
    check.add_argument("--format", choices=FORMATS, default="text")
    add_color_option(check)
    add_include_option(check)
    add_exclude_option(check)
    check.set_defaults(func=run)


def normalize_argv(argv: list[str]) -> list[str]:
    """``check GROUP... PATH...`` means ``check --group GROUP... PATH...``."""
    args = list(argv)
    if args[:1] != ["check"]:
        return args
    i = 1
    while i < len(args) and args[i] in GROUPS:
        args[i : i + 1] = ["--group", args[i]]
        i += 2
    return args


def _retired(args: argparse.Namespace) -> frozenset[str]:
    names: list[str] = list(args.retired)
    for path in args.retired_file:
        try:
            names += read_retired(path)
        except (OSError, UnicodeDecodeError) as error:
            raise InputError(f"{Path(path).as_posix()}: {error}") from error
    if not names:
        raise InputError("retired: no names; set check.retired or check.retired-file")
    return frozenset(names)


def collect_findings(args: argparse.Namespace) -> list[Finding]:
    groups: set[str] = set(args.groups or DEFAULT_GROUPS)
    retired = _retired(args) if "retired" in groups else None
    paths: list[Path] = args.paths
    linking = [p for p in paths if p.suffix in LINK_SUFFIXES and p.is_file()]
    if linking and "links" not in groups:
        raise InputError(f"{linking[0].as_posix()}: only the links group reads it")
    rest = [p for p in paths if p not in linking]
    workspace = load(rest or ([] if linking else [Path()]), args.include, args.exclude)
    workspace.note_skipped("check")
    findings: list[Finding] = []
    if "project" in groups:
        for project in workspace.projects:
            findings += check_project(project)
    readable: list[SourceFile] = []
    for source in workspace.sources:
        data = source.path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            if "syntax" in groups:
                findings.append(invalid_utf8(source.path, data, error))
            continue
        readable.append(source)
        if "hygiene" in groups:
            findings += check_hygiene(source.path, text)
        if retired is not None:
            findings += check_retired(source.path, text, retired)
    parsed: dict[Path, Theory] = {}
    if groups & {"proofs", "syntax", "symbols", "docs", "leftovers", "methods", "prose"}:
        for source in readable:
            theory = parsed[source.path] = source.parse()
            if "proofs" in groups:
                findings += check_proofs(source.path, theory)
            if "syntax" in groups:
                findings += check_syntax(source.path, theory)
                findings += check_theory_name(source.path, theory)
            if "leftovers" in groups:
                findings += check_leftovers(source.path, theory)
            if "methods" in groups:
                findings += check_methods(source.path, theory)
            if "symbols" in groups:
                findings += check_symbols(
                    source.path, theory, include_comments=args.include_comments
                )
            if "docs" in groups:
                findings += check_docs(source.path, theory)
    if "locales" in groups:
        findings += check_locales(readable, allow=args.allow)
    if "notation" in groups:
        findings += check_notation(readable, allow=args.allow)
    if "unused" in groups:
        findings += check_unused(readable, allow=args.allow, leaves=args.leaf_session)
    if "redundant" in groups:
        findings += check_redundant(readable)
    if "prose" in groups:
        findings += check_prose(readable, parsed, allow=args.allow)
    if "links" in groups:
        projects = workspace.projects or [Project.load(Path(), args.include)]
        findings += check_links(linking, projects, args.browser_info, args.link_base)
    ignored = set(args.ignore)
    return sorted(unsuppressed({f for f in findings if f.code not in ignored}))


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
    "notation": "cyan",
    "unused": "magenta",
    "redundant": "magenta",
    "hygiene": "magenta",
    "leftovers": "yellow",
    "methods": "yellow",
    "retired": "red",
    "prose": "green",
    "links": "blue",
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
