"""``isar fmt``: format theory files."""

import argparse
import difflib
import sys
from pathlib import Path

from isar_tools.formatter.formatter import FormatError, Options, format_theory
from isar_tools.project.workspace import add_include_option, collect
from isar_tools.render import display_path
from isar_tools.source.files import write_source
from isar_tools.source.theory import parse_theory


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:  # pyright: ignore[reportPrivateUsage]
    fmt = sub.add_parser(
        "fmt",
        help="Format Isabelle/Isar source files",
        description="Format .thy files in place. Only layout changes: indentation, trailing "
        "whitespace, and blank lines. `-` reads standard input and writes standard output.",
    )
    fmt.add_argument("paths", nargs="+", type=Path, help=".thy files or directories, or -")
    mode = fmt.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="only list files that would change; exit 1 if any"
    )
    mode.add_argument(
        "--diff", action="store_true", help="print a unified diff instead of writing; exit 1 if any"
    )
    fmt.add_argument(
        "--normalize",
        action="store_true",
        help="set indentation exactly; by default lines are only indented further, never less",
    )
    fmt.add_argument("--indent", type=int, default=2, metavar="N", help="indent step (default: 2)")
    fmt.add_argument(
        "--max-blank-lines",
        type=int,
        default=2,
        metavar="N",
        help="collapse longer runs of blank lines (default: 2)",
    )
    add_include_option(fmt)
    fmt.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    options = Options(
        indent=args.indent, max_blank_lines=args.max_blank_lines, normalize=args.normalize
    )
    if [str(p) for p in args.paths] == ["-"]:
        return _stdin(options)
    status = 0
    changed = 0
    for source in collect(args.paths, args.include):
        name = display_path(source.path)
        before = source.read()
        try:
            after = format_theory(parse_theory(before, source.keywords()), options)
        except FormatError as error:
            print(f"isar fmt: {name}: {error}; not formatted", file=sys.stderr)
            status = 2
            continue
        if after == before:
            continue
        changed += 1
        if args.check:
            print(name)
        elif args.diff:
            sys.stdout.writelines(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=f"a/{name}",
                    tofile=f"b/{name}",
                )
            )
        else:
            write_source(source.path, after)
            print(f"formatted {name}", file=sys.stderr)
    if (args.check or args.diff) and changed:
        status = max(status, 1)
    return status


def _stdin(options: Options) -> int:
    text = sys.stdin.buffer.read().decode("utf-8")
    try:
        sys.stdout.buffer.write(format_theory(parse_theory(text), options).encode("utf-8"))
    except FormatError as error:
        print(f"isar fmt: <stdin>: {error}", file=sys.stderr)
        return 2
    return 0
