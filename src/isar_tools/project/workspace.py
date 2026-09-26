"""Theory files named on a command line, with the context needed to parse them.

A path argument is either a ``.thy`` file or a directory. A directory is loaded
as a project (see ``Project.load``); every ``.thy`` file below it is included,
whether or not a session reaches it. A file is parsed with the project of its
directory.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from isar_tools.project.model import SKIP_DIRS, Project
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
        return self.path.read_text(encoding="utf-8")

    def parse(self) -> Theory:
        return parse_theory(self.read(), self.keywords())


class InputError(Exception):
    """A path argument that does not exist or is not a theory file."""


def _thy_files(directory: Path) -> list[Path]:
    return sorted(
        p.resolve()
        for p in directory.rglob("*.thy")
        if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(directory).parts)
    )


def project_root(path: Path) -> Path:
    """The nearest ancestor of ``path`` with a ``ROOT`` or ``ROOTS`` file."""
    for directory in path.resolve().parents:
        if (directory / "ROOT").is_file() or (directory / "ROOTS").is_file():
            return directory
    return path.resolve().parent


def collect(paths: Iterable[Path]) -> list[SourceFile]:
    """Theory files named by ``paths``, each once, in argument order."""
    found: dict[Path, SourceFile] = {}
    projects: dict[Path, Project] = {}

    def project_of(directory: Path) -> Project:
        directory = directory.resolve()
        if directory not in projects:
            projects[directory] = Project.load(directory)
        return projects[directory]

    for path in paths:
        if path.is_dir():
            project = project_of(path)
            for thy in _thy_files(path):
                found.setdefault(thy, SourceFile(thy, project))
        elif path.is_file() and path.suffix == ".thy":
            resolved = path.resolve()
            found.setdefault(resolved, SourceFile(resolved, project_of(project_root(resolved))))
        elif path.exists():
            raise InputError(f"{path}: not a directory or .thy file")
        else:
            raise InputError(f"{path}: no such file or directory")
    return list(found.values())
