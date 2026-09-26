"""Command-line entry point.

Exit status: 0 success, 1 check failure or differences found,
2 invalid invocation or unreadable input. Data goes to stdout,
diagnostics to stderr.
"""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version

from isar_tools.project.workspace import InputError
from isar_tools.stats import cli as stats_cli

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

# Commands not implemented yet.
PLACEHOLDERS: dict[str, str] = {
    "fmt": "Format Isabelle/Isar source files",
    "check": "Check project and source hygiene",
    "project": "Inspect Isabelle project structure",
    "symbols": "Inspect or normalize Isabelle symbols",
}


def _placeholder(args: argparse.Namespace) -> int:
    print(f"isar {args.command}: not implemented yet", file=sys.stderr)
    return EXIT_USAGE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="isar", description="Source tooling for Isabelle/Isar.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('isar-tools')}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    stats_cli.register(sub)
    for name, summary in PLACEHOLDERS.items():
        sub.add_parser(name, help=summary, description=summary).set_defaults(func=_placeholder)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(stats_cli.normalize_argv(sys.argv[1:] if argv is None else argv))
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        return args.func(args)
    except InputError as error:
        print(f"isar {args.command}: {error}", file=sys.stderr)
        return EXIT_USAGE
