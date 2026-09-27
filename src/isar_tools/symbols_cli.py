"""``isar symbols``: convert between ASCII and Unicode symbol spellings."""

import argparse
import sys
from pathlib import Path

from isar_tools.project.workspace import collect
from isar_tools.render import display_path
from isar_tools.source.files import read_source, write_source
from isar_tools.source.symbols import decode, encode
from isar_tools.style import Style, add_color_option, write_diff


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:  # pyright: ignore[reportPrivateUsage]
    symbols = sub.add_parser(
        "symbols",
        help="Inspect or normalize Isabelle symbols",
        description="Inspect or normalize Isabelle symbols.",
    )
    actions = symbols.add_subparsers(dest="action", metavar="<action>", required=True)
    normalize = actions.add_parser(
        "normalize",
        help="rewrite symbols as \\<name> (default) or as Unicode",
        description="Rewrite every known Isabelle symbol in .thy files as its ASCII "
        "spelling \\<name> (the default), or as its Unicode rendering. Characters without "
        "an Isabelle symbol are left alone. Files are rewritten in place unless --check or "
        "--diff is given.",
    )
    normalize.add_argument("paths", nargs="+", type=Path, help=".thy files or directories")
    normalize.add_argument("--to", choices=("ascii", "unicode"), default="ascii")
    mode = normalize.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="only list files that would change; exit 1 if any"
    )
    mode.add_argument(
        "--diff", action="store_true", help="print a unified diff instead of writing; exit 1 if any"
    )
    add_color_option(normalize)
    normalize.set_defaults(func=run_normalize)


def run_normalize(args: argparse.Namespace) -> int:
    convert = encode if args.to == "ascii" else decode
    changed = 0
    for source in collect(args.paths):
        before = read_source(source.path)
        after = convert(before)
        if after == before:
            continue
        changed += 1
        name = display_path(source.path)
        if args.check:
            print(name)
        elif args.diff:
            write_diff(before, after, name, sys.stdout, Style.for_stream(args.color, sys.stdout))
        else:
            write_source(source.path, after)
            print(f"normalized {name}", file=sys.stderr)
    if args.check or args.diff:
        return 1 if changed else 0
    return 0
