"""``isar fmt``: format theory files."""

import argparse
import sys
from pathlib import Path

from isar_tools.config import add_exclude_option
from isar_tools.formatter.formatter import FormatError, Options
from isar_tools.formatter.wrap import format_source
from isar_tools.project.workspace import add_include_option, load
from isar_tools.render import display_path
from isar_tools.source.files import write_source
from isar_tools.style import Style, add_color_option, write_diff


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:  # pyright: ignore[reportPrivateUsage]
    fmt = sub.add_parser(
        "fmt",
        help="Format Isabelle/Isar source files",
        description="Format .thy files in place. Only layout changes: indentation, trailing "
        "whitespace, blank lines, and, with --max-line-length, line breaks at spaces between "
        "tokens. `-` reads standard input and writes standard output.",
    )
    fmt.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path()],
        help=".thy files or directories (default: the current directory), or -",
    )
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
        default=None,
        help="set indentation exactly; by default lines are only indented further, never less",
    )
    fmt.add_argument("--indent", type=int, metavar="N", help="indent step (default: 2)")
    fmt.add_argument(
        "--max-blank-lines",
        type=int,
        metavar="N",
        help="collapse longer runs of blank lines (default: 2)",
    )
    fmt.add_argument(
        "--max-line-length",
        type=int,
        metavar="N",
        help="wrap lines longer than N Isabelle symbols at spaces between tokens "
        "(default: off; 0 turns off wrapping set in the configuration file)",
    )
    add_include_option(fmt)
    add_exclude_option(fmt)
    add_color_option(fmt)
    fmt.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    options = Options(
        indent=args.indent,
        max_blank_lines=args.max_blank_lines,
        normalize=args.normalize,
        max_line_length=args.max_line_length,
    )
    if [str(p) for p in args.paths] == ["-"]:
        return _stdin(options)
    status = 0
    changed = 0
    workspace = load(args.paths, args.include, args.exclude)
    workspace.note_skipped("fmt")
    for source in workspace.sources:
        name = display_path(source.path)
        before = source.read()
        try:
            after = format_source(before, source.keywords(), options)
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
            write_diff(before, after, name, sys.stdout, Style.for_stream(args.color, sys.stdout))
        else:
            write_source(source.path, after)
            print(f"formatted {name}", file=sys.stderr)
    if (args.check or args.diff) and changed:
        status = max(status, 1)
    return status


def _stdin(options: Options) -> int:
    text = sys.stdin.buffer.read().decode("utf-8")
    try:
        sys.stdout.buffer.write(format_source(text, None, options).encode("utf-8"))
    except FormatError as error:
        print(f"isar fmt: <stdin>: {error}", file=sys.stderr)
        return 2
    return 0
