"""Theory files named on a command line, with the context needed to parse them.

A path argument is either a ``.thy`` file or a directory. A directory is loaded
as a project (see ``Project.load``); every ``.thy`` file below it is included,
whether or not a session reaches it, except those of other projects nested in
it: ``-d`` directories, and directories with their own ``ROOT`` or ``ROOTS``
that hold none of the project's sessions (a vendored submodule, say). A file is
parsed with the project of its directory.
"""

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.project.model import SKIP_DIRS, Project
from isar_tools.render import display_path
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


def foreign_projects(directory: Path, project: Project) -> list[Path]:
    """Directories below ``directory`` with their own ``ROOT`` or ``ROOTS``
    that hold none of ``project``'s sessions: other projects, such as a
    vendored submodule that ``ROOTS`` does not list."""
    root = directory.resolve()
    own = [s.dir.resolve() for s in project.own_sessions]
    found: set[Path] = set()
    for marker in ("ROOT", "ROOTS"):
        for path in root.rglob(marker):
            d = path.parent.resolve()
            if d == root or not path.is_file():
                continue
            if SKIP_DIRS.intersection(d.relative_to(root).parts):
                continue
            if not any(s == d or s.is_relative_to(d) for s in own):
                found.add(d)
    # Only the outermost: a foreign project's own sessions are not ours either.
    return sorted(d for d in found if not any(d != o and d.is_relative_to(o) for o in found))


def _thy_files(directory: Path, excluded: Sequence[Path] = ()) -> list[Path]:
    """Theory files below ``directory``, except those of ``excluded``
    directories nested in it: an AFP or a vendored submodule inside a project
    provides sessions to resolve against, not files to check or format."""
    root = directory.resolve()
    nested = [d.resolve() for d in excluded]
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
    # Nested directories of other projects, skipped (see ``foreign_projects``).
    skipped: list[Path] = field(default_factory=list[Path])

    def note_skipped(self, command: str) -> None:
        """Tell the user, on stderr, which nested projects were left out."""
        for directory in self.skipped:
            print(
                f"isar {command}: note: skipped {display_path(directory)}: another project "
                "(its own ROOT, none of the sessions); pass it with -d to resolve against it",
                file=sys.stderr,
            )


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
    skipped: list[Path] = []
    for path in paths:
        if path.is_dir():
            project = project_of(path)
            if project not in named:
                named.append(project)
            foreign = foreign_projects(path, project)
            included = {d.resolve() for d in include}
            skipped += [d for d in foreign if d not in included and d not in skipped]
            for thy in _thy_files(path, [*include, *foreign]):
                found.setdefault(thy, SourceFile(thy, project))
        elif path.is_file() and path.suffix == ".thy":
            resolved = path.resolve()
            found.setdefault(resolved, SourceFile(resolved, project_of(project_root(resolved))))
        elif path.exists():
            raise InputError(f"{path.as_posix()}: not a directory or .thy file")
        else:
            raise InputError(f"{path.as_posix()}: no such file or directory")
    return Workspace(list(found.values()), named, skipped)


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
