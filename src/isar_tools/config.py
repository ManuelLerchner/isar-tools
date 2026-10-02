"""Per-project options: ``[tool.isar]`` in ``pyproject.toml``, or ``isar.toml``.

The file is found by searching upward from the working directory; the first
``isar.toml``, or ``pyproject.toml`` with a ``[tool.isar]`` table, wins. In
``isar.toml`` the keys are at the top level::

    include = ["$AFP", "vendor/td-verification"]   # like -d
    exclude = ["src/**/generated/**"]              # like --exclude

    [fmt]
    max-line-length = 100
    indent = 2
    max-blank-lines = 2
    normalize = false

    [check]
    groups = ["project", "proofs", "syntax"]
    ignore = ["oops"]
    allow = ["some_name"]
    leaf-sessions = ["Examples"]
    retired = ["old_name"]
    retired-file = "retired_identifiers.txt"

    [stats]
    max-line-length = 100
    watch = ["metis", "smt"]

Relative paths and globs are relative to the file's directory. ``$VAR`` and
``${VAR}`` in ``include`` are expanded; an entry whose variable is unset, or
whose directory does not exist, is skipped with a note, so one file serves
machines with and without an AFP checkout. Command-line options take
precedence; ``-d`` and ``--exclude`` add to the configured lists.
"""

import argparse
import os
import re
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from isar_tools.checks.findings import CODES, GROUPS

FILE = "isar.toml"
PYPROJECT = "pyproject.toml"


class ConfigError(Exception):
    """An unreadable or invalid configuration file."""


@dataclass(frozen=True)
class Exclude:
    """A glob, relative to ``base``: ``*`` and ``?`` stay within one path
    component, ``**`` spans any number of them."""

    base: Path
    glob: str

    def matches(self, path: Path) -> bool:
        """Whether ``path`` or one of its parent directories matches."""
        try:
            rel = path.resolve().relative_to(self.base.resolve())
        except ValueError:
            return False
        pattern = _compile(self.glob)
        parts = rel.parts
        return any(pattern.fullmatch("/".join(parts[:n])) for n in range(1, len(parts) + 1))


def _compile(glob: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    glob = glob.strip("/")
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out))


@dataclass
class Config:
    path: Path | None = None
    include: list[Path] = field(default_factory=list[Path])
    exclude: list[Exclude] = field(default_factory=list[Exclude])
    fmt: dict[str, object] = field(default_factory=dict[str, object])
    check: dict[str, object] = field(default_factory=dict[str, object])
    stats: dict[str, object] = field(default_factory=dict[str, object])


_SECTIONS: dict[str, dict[str, type]] = {
    "fmt": {"max-line-length": int, "indent": int, "max-blank-lines": int, "normalize": bool},
    "check": {
        "groups": list,
        "ignore": list,
        "allow": list,
        "leaf-sessions": list,
        "retired": list,
        "retired-file": str,
    },
    "stats": {"max-line-length": int, "watch": list},
}


def find(start: Path) -> tuple[Path, dict[str, object]] | None:
    """The first configuration file at or above ``start``, with its table."""
    for directory in [start.resolve(), *start.resolve().parents]:
        candidate = directory / FILE
        if candidate.is_file():
            return candidate, _read(candidate)
        candidate = directory / PYPROJECT
        if candidate.is_file():
            tool = _read(candidate).get("tool", {})
            if isinstance(tool, dict) and "isar" in tool:
                table = cast(dict[str, object], tool)["isar"]
                if not isinstance(table, dict):
                    raise ConfigError(f"{candidate.as_posix()}: [tool.isar] must be a table")
                return candidate, cast(dict[str, object], table)
    return None


def _read(path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as err:  # TOMLDecodeError and UnicodeDecodeError
        raise ConfigError(f"{path.as_posix()}: {err}") from err


def _strings(where: str, value: object) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(v, str) for v in cast(list[object], value)
    ):
        raise ConfigError(f"{where}: expected a list of strings")
    return cast(list[str], value)


def parse(path: Path, table: dict[str, object]) -> Config:
    """Validate ``table`` (read from ``path``) into a ``Config``."""
    where = path.as_posix()
    base = path.parent
    config = Config(path)
    for key, value in table.items():
        if key == "include":
            for entry in _strings(f"{where}: include", value):
                expanded = os.path.expandvars(entry)
                directory = base / expanded
                if "$" in expanded or not directory.is_dir():
                    _note(f"{where}: include {entry!r}: not a directory here; skipped")
                    continue
                config.include.append(directory)
        elif key == "exclude":
            config.exclude += [Exclude(base, g) for g in _strings(f"{where}: exclude", value)]
        elif key in _SECTIONS:
            if not isinstance(value, dict):
                raise ConfigError(f"{where}: [{key}] must be a table")
            section = cast(dict[str, object], value)
            for name, item in section.items():
                expected = _SECTIONS[key].get(name)
                if expected is None:
                    raise ConfigError(f"{where}: [{key}] has no option {name!r}")
                if expected is list:
                    item = _strings(f"{where}: {key}.{name}", item)
                elif not isinstance(item, expected) or (expected is int and isinstance(item, bool)):
                    raise ConfigError(f"{where}: {key}.{name}: expected {expected.__name__}")
                getattr(config, key)[name] = item
        else:
            raise ConfigError(f"{where}: unknown option {key!r}")
    _validate_check(where, config.check)
    if "retired-file" in config.check:
        config.check["retired-file"] = base / cast(str, config.check["retired-file"])
    return config


def _validate_check(where: str, check: dict[str, object]) -> None:
    for group in cast(list[str], check.get("groups", [])):
        if group not in (*GROUPS, "all"):
            raise ConfigError(f"{where}: check.groups: unknown group {group!r}")
    for code in cast(list[str], check.get("ignore", [])):
        if code not in CODES:
            raise ConfigError(f"{where}: check.ignore: unknown code {code!r}")


def _note(message: str) -> None:
    print(f"isar: note: {message}", file=sys.stderr)


def load(start: Path) -> Config:
    """The configuration that applies in ``start``; empty if there is none."""
    found = find(start)
    return parse(*found) if found is not None else Config()


def _default(args: argparse.Namespace, name: str, value: object) -> None:
    """Set ``args.name`` to ``value`` unless the command line gave it."""
    if getattr(args, name, None) is None:
        setattr(args, name, value)


# Built-in defaults of the options a configuration file can set. The parsers
# leave these options None, so a value from the file can fill them in.
FMT_DEFAULTS: dict[str, object] = {
    "indent": 2,
    "max_blank_lines": 2,
    "max_line_length": None,
    "normalize": False,
}
STATS_DEFAULTS: dict[str, object] = {"max_line_length": 100}


def apply(config: Config, args: argparse.Namespace) -> None:
    """Fill ``args`` from ``config`` where the command line left them open."""
    if hasattr(args, "include"):
        args.include = [*config.include, *args.include]
    if hasattr(args, "exclude"):
        cwd = Path.cwd()
        args.exclude = [*config.exclude, *(Exclude(cwd, g) for g in args.exclude)]
    command = getattr(args, "command", None)
    if command == "fmt":
        for name, default in FMT_DEFAULTS.items():
            _default(args, name, config.fmt.get(name.replace("_", "-"), default))
        if args.max_line_length == 0:  # `--max-line-length 0` turns configured wrapping off
            args.max_line_length = None
    elif command == "check":
        _default(args, "groups", config.check.get("groups"))
        args.ignore = [*cast(Sequence[str], config.check.get("ignore", [])), *args.ignore]
        args.allow = [*cast(Sequence[str], config.check.get("allow", [])), *args.allow]
        leaves = cast(Sequence[str], config.check.get("leaf-sessions", []))
        args.leaf_session = [*leaves, *args.leaf_session]
        args.retired = [*cast(Sequence[str], config.check.get("retired", [])), *args.retired]
        if "retired-file" in config.check:
            args.retired_file = [config.check["retired-file"], *args.retired_file]
    elif command == "stats" and hasattr(args, "max_line_length"):
        for name, default in STATS_DEFAULTS.items():
            _default(args, name, config.stats.get(name.replace("_", "-"), default))
        _default(args, "watch", config.stats.get("watch"))


def add_exclude_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="leave out files matching GLOB, relative to the working directory; `**` spans "
        "directories (repeatable; adds to `exclude` in the configuration file)",
    )
