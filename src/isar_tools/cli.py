"""Command-line entry point.

Exit status: 0 success, 1 check failure or differences found,
2 invalid invocation or unreadable input. Data goes to stdout,
diagnostics to stderr.
"""

import argparse
import sys
from collections.abc import Sequence

from isar_tools import __version__

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

COMMANDS: dict[str, str] = {
    "fmt": "Format Isabelle/Isar source files",
    "check": "Check project and source hygiene",
    "stats": "Report source, proof, and build statistics",
    "project": "Inspect Isabelle project structure",
    "symbols": "Inspect or normalize Isabelle symbols",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="isar", description="Source tooling for Isabelle/Isar.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, summary in COMMANDS.items():
        sub.add_parser(name, help=summary, description=summary)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command: str | None = args.command
    if command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    print(f"isar {command}: not implemented yet", file=sys.stderr)
    return EXIT_USAGE
