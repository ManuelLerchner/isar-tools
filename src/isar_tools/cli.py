"""Command-line entry point.

Exit status: 0 success, 1 check failure or differences found,
2 invalid invocation or unreadable input. Data goes to stdout,
diagnostics to stderr.
"""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version

from isar_tools import symbols_cli
from isar_tools.checks import cli as check_cli
from isar_tools.formatter import cli as fmt_cli
from isar_tools.project import cli as project_cli
from isar_tools.project.workspace import InputError
from isar_tools.stats import cli as stats_cli

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="isar", description="Source tooling for Isabelle/Isar.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('isar-tools')}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    fmt_cli.register(sub)
    stats_cli.register(sub)
    check_cli.register(sub)
    project_cli.register(sub)
    symbols_cli.register(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(check_cli.normalize_argv(stats_cli.normalize_argv(raw)))
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        return args.func(args)
    except InputError as error:
        print(f"isar {args.command}: {error}", file=sys.stderr)
        return EXIT_USAGE
