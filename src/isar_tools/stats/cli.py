"""``isar stats``: source and proof statistics."""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from isar_tools.project.workspace import collect
from isar_tools.render import RENDERERS, Table
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
        description="Report source and proof statistics. `isar stats PATH` shows the summary.",
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


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """``stats PATH ...`` means ``stats summary PATH ...``."""
    args = list(argv)
    if args[:1] == ["stats"] and (len(args) == 1 or args[1] not in (*VIEWS, "-h", "--help")):
        args.insert(1, "summary")
    return args


def run(args: argparse.Namespace) -> int:
    watched = frozenset(args.watch or DEFAULT_WATCHED)
    entries: list[Entry] = []
    for source in collect(args.paths):
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
