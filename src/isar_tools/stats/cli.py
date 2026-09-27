"""``isar stats``: source, proof, and build statistics."""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from isar_tools.project.workspace import InputError, add_include_option, collect
from isar_tools.render import RENDERERS, Table
from isar_tools.stats.build import (
    BuildLogError,
    budgets_table,
    check_budgets,
    parse_build_log,
    reelaboration_table,
)
from isar_tools.stats.build import sessions_table as build_sessions_table
from isar_tools.stats.metrics import theory_stats
from isar_tools.stats.views import (
    THEORY_SORTS,
    Entry,
    commands_table,
    proofs_table,
    sessions_table,
    style_table,
    theories_table,
)

DEFAULT_WATCHED = ("metis", "smt", "sledgehammer")

VIEWS: dict[str, str] = {
    "summary": "sessions, then the largest theories (default)",
    "sessions": "per-session totals and proof-length distribution",
    "theories": "per-theory size, proofs, and long lines",
    "proofs": "the longest proofs",
    "commands": "command usage per session",
    "style": "theories that are too long, have long lines, unfinished proofs, or watched methods",
}

BUILD_VIEW = "build"
BUILD_SUMMARY = "where theory elaboration time went in an `isabelle build -v` log"


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths", nargs="*", type=Path, default=[Path()], help="project directories or .thy files"
    )
    parser.add_argument("--format", choices=sorted(RENDERERS), default="text")
    parser.add_argument(
        "--session", action="append", metavar="NAME", help="only these sessions (repeatable)"
    )
    parser.add_argument(
        "--max-line-length",
        type=int,
        default=100,
        metavar="N",
        help="a line longer than N Isabelle symbols is long (default: 100)",
    )
    parser.add_argument(
        "--watch",
        action="append",
        metavar="METHOD",
        help=f"count uses of this proof method (repeatable; default: {' '.join(DEFAULT_WATCHED)})",
    )
    add_include_option(parser)


def _top(parser: argparse.ArgumentParser, default: int) -> None:
    parser.add_argument(
        "--top",
        type=int,
        default=default,
        metavar="N",
        help=f"rows to show, 0 for all (default: {default})",
    )


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:  # pyright: ignore[reportPrivateUsage]
    stats = sub.add_parser(
        "stats",
        help="Report source, proof, and build statistics",
        description=(
            "Report source, proof, and build statistics. `isar stats PATH` shows the summary."
        ),
    )
    views = stats.add_subparsers(dest="view", metavar="<view>")
    for name, summary in VIEWS.items():
        view = views.add_parser(name, help=summary, description=summary)
        _common(view)
        if name in ("summary", "theories"):
            view.add_argument("--sort", choices=sorted(THEORY_SORTS), default="lines")
            _top(view, 20)
        if name == "proofs":
            _top(view, 20)
        if name == "style":
            view.add_argument("--max-theory-lines", type=int, default=1500, metavar="N")
        view.set_defaults(func=run)
    _register_build(views)


def _budget(spec: str) -> tuple[str, int]:
    session, sep, count = spec.partition("=")
    if not sep or not session or not count.isdigit():
        raise argparse.ArgumentTypeError(f"expected SESSION=N with N >= 0, got {spec!r}")
    return session, int(count)


def _register_build(views: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:  # pyright: ignore[reportPrivateUsage]
    build = views.add_parser(
        BUILD_VIEW,
        help=BUILD_SUMMARY,
        description=(
            f"Report {BUILD_SUMMARY}: per-session totals and theories elaborated more "
            "than once. Only lines `SESSION: theory OWNER.THEORY 100% (Ns cumulated time)` "
            "are read."
        ),
    )
    build.add_argument("log", type=Path, metavar="BUILD_LOG", help="output of `isabelle build -v`")
    build.add_argument("--format", choices=sorted(RENDERERS), default="text")
    _top(build, 10)
    build.add_argument(
        "--budget",
        action="append",
        type=_budget,
        default=[],
        metavar="SESSION=N",
        help=(
            "allow at most N elaborations of SESSION's theories inside other sessions; "
            "exceeding it is exit status 1 (repeatable)"
        ),
    )
    build.add_argument(
        "--allow-empty",
        action="store_true",
        help="a log without theory elaboration lines is not an error (an incremental build "
        "that rebuilt nothing); report nothing and exit 0",
    )
    build.set_defaults(func=run_build)


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """``stats PATH ...`` means ``stats summary PATH ...``."""
    args = list(argv)
    if args[:1] == ["stats"] and (
        len(args) == 1 or args[1] not in (*VIEWS, BUILD_VIEW, "-h", "--help")
    ):
        args.insert(1, "summary")
    return args


def run(args: argparse.Namespace) -> int:
    watched = frozenset(args.watch or DEFAULT_WATCHED)
    entries: list[Entry] = []
    for source in collect(args.paths, args.include):
        if args.session and source.session not in args.session:
            continue
        stats = theory_stats(source.parse(), max_line_length=args.max_line_length, methods=watched)
        entries.append(Entry(source.session, source.path, stats))
    if not entries:
        print("isar stats: no .thy files found", file=sys.stderr)
        return 2

    builders: dict[str, Callable[[], list[Table]]] = {
        "summary": lambda: [sessions_table(entries), theories_table(entries, args.sort, args.top)],
        "sessions": lambda: [sessions_table(entries)],
        "theories": lambda: [theories_table(entries, args.sort, args.top)],
        "proofs": lambda: [proofs_table(entries, args.top)],
        "commands": lambda: [commands_table(entries)],
        "style": lambda: [style_table(entries, max_theory_lines=args.max_theory_lines)],
    }
    RENDERERS[args.format](builders[args.view](), sys.stdout)
    return 0


def run_build(args: argparse.Namespace) -> int:
    path: Path = args.log
    budgets: dict[str, int] = {}
    for session, count in args.budget:
        if session in budgets:
            raise InputError(f"--budget {session} given twice")
        budgets[session] = count
    if not path.is_file():
        raise InputError(f"{path.as_posix()}: no such file")
    try:
        with path.open(encoding="utf-8", errors="replace") as lines:
            log = parse_build_log(lines)
    except OSError as error:
        raise InputError(f"{path.as_posix()}: {error.strerror}") from error
    except BuildLogError as error:
        raise InputError(f"{path.as_posix()}: {error}") from error
    if not log.elaborations and args.allow_empty:
        print(
            f"isar stats build: {path.as_posix()}: no theory elaboration lines; nothing to report",
            file=sys.stderr,
        )
        return 0
    if not log.elaborations:
        raise InputError(
            f"{path.as_posix()}: no theory elaboration lines "
            "(`SESSION: theory OWNER.THEORY 100% (Ns cumulated time)`) in "
            f"{log.lines} lines. Either nothing was rebuilt, or this is not an "
            "`isabelle build -v` log; a clean build (`isabelle build -c -v`) has them. "
            "Pass --allow-empty to accept an incremental build that rebuilt nothing."
        )
    results = check_budgets(log, budgets)
    tables = [build_sessions_table(log), reelaboration_table(log, args.top)]
    if results:
        tables.append(budgets_table(results))
    RENDERERS[args.format](tables, sys.stdout)
    failed = [r for r in results if not r.ok]
    for result in failed:
        print(f"isar stats build: over budget: {result.message()}", file=sys.stderr)
    return 1 if failed else 0
