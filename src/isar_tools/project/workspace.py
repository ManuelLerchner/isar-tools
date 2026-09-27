"""Theory files named on a command line, with the context needed to parse them.

A path argument is either a ``.thy`` file or a directory. A directory is loaded
as a project (see ``Project.load``); every ``.thy`` file below it is included,
whether or not a session reaches it. A file is parsed with the project of its
directory.
"""

import argparse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from isar_tools.project.model import SKIP_DIRS, Project
from isar_tools.source.files import read_source
from isar_tools.source.keywords import CommandKind
from isar_tools.source.theory import Theory, parse_theory

NO_SESSION = "-"


@dataclass(frozen=True)
class SourceFile:
    path: Path
    project: Project

    @property
    def session(self) -> str:
        session = self.project.session_of(self.path)
        return session.name if session is not None else NO_SESSION

    def keywords(self) -> dict[str, CommandKind]:
        return self.project.keywords_for(self.path)

    def read(self) -> str:
        return read_source(self.path)

    def parse(self) -> Theory:
        return parse_theory(self.read(), self.keywords())


class InputError(Exception):
    """A path argument that does not exist or is not a theory file."""


def _thy_files(directory: Path, include: Sequence[Path] = ()) -> list[Path]:
    """Theory files below ``directory``, except those of ``include``
    directories nested in it: an AFP or a vendored submodule inside a project
    provides sessions to resolve against, not files to check or format."""
    root = directory.resolve()
    nested = [d.resolve() for d in include]
    nested = [d for d in nested if d != root and d.is_relative_to(root)]
    return sorted(
        p.resolve()
        for p in directory.rglob("*.thy")
        if p.is_file()
        and not SKIP_DIRS.intersection(p.relative_to(directory).parts)
        and not any(p.resolve().is_relative_to(d) for d in nested)
    )


def project_root(path: Path) -> Path:
    """The nearest ancestor of ``path`` with a ``ROOT`` or ``ROOTS`` file."""
    for directory in path.resolve().parents:
        if (directory / "ROOT").is_file() or (directory / "ROOTS").is_file():
            return directory
    return path.resolve().parent


@dataclass(frozen=True)
class Workspace:
    sources: list[SourceFile]
    # Projects of the directory arguments, in argument order. A file argument
    # loads its project only to parse the file, so it adds none.
    projects: list[Project]


def load(paths: Iterable[Path], include: Sequence[Path] = ()) -> Workspace:
    """Theory files named by ``paths``, each once, in argument order, and the
    projects they were loaded with. ``include`` directories resolve imports and
    keywords, like ``isabelle build -d``."""
    found: dict[Path, SourceFile] = {}
    projects: dict[Path, Project] = {}

    def project_of(directory: Path) -> Project:
        directory = directory.resolve()
        if directory not in projects:
            projects[directory] = Project.load(directory, include)
        return projects[directory]

    named: list[Project] = []
    for path in paths:
        if path.is_dir():
            project = project_of(path)
            if project not in named:
                named.append(project)
            for thy in _thy_files(path, include):
                found.setdefault(thy, SourceFile(thy, project))
        elif path.is_file() and path.suffix == ".thy":
            resolved = path.resolve()
            found.setdefault(resolved, SourceFile(resolved, project_of(project_root(resolved))))
        elif path.exists():
            raise InputError(f"{path.as_posix()}: not a directory or .thy file")
        else:
            raise InputError(f"{path.as_posix()}: no such file or directory")
    return Workspace(list(found.values()), named)


def collect(paths: Iterable[Path], include: Sequence[Path] = ()) -> list[SourceFile]:
    """Theory files named by ``paths``, each once, in argument order."""
    return load(paths, include).sources


def _directory(value: str) -> Path:
    """An existing directory: a mistyped ``-d`` must not silently drop the
    commands and imports it was meant to provide."""
    path = Path(value)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"{value}: not a directory")
    return path


def add_include_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-d",
        dest="include",
        action="append",
        type=_directory,
        default=[],
        metavar="DIR",
        help="also read the sessions of DIR to resolve imports and commands, like "
        "`isabelle build -d` (repeatable)",
    )
