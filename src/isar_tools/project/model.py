"""Isabelle projects: ROOT discovery, sessions, and theory resolution.

Resolution follows Isabelle's rules as far as they are visible without the
prover:

- A ``theories`` entry ``S.T`` names theory ``T`` of session ``S``. Any other
  entry is a path relative to the session directory, with ``.thy`` implied,
  looked up in the session directory and its ``directories``.
- An import ``S.T`` names theory ``T`` of session ``S``. An unqualified import
  is first a path relative to the importing file's directory, then a theory of
  the importing session.
- Sessions outside the project (``HOL``, AFP entries not scanned, ...) are
  external: their theories resolve to nothing and are not an error.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.project.root import Diagnostic, RootFile, RootSession, read_root
from isar_tools.source.keywords import BUILTIN_COMMANDS, CommandKind
from isar_tools.source.theory import Header, Name, keyword_table, read_header

SKIP_DIRS = frozenset({".git", ".hg", ".svn", ".pixi", "node_modules", "__pycache__"})


@dataclass(frozen=True)
class Problem:
    """A project-level finding at a file position (1-based line, 0 if none)."""

    path: Path
    line: int
    message: str


@dataclass
class Session:
    spec: RootSession
    root: RootFile
    dir: Path
    search_dirs: list[Path]
    # theory name -> file, for every entry and import this session resolves
    theories: dict[str, Path] = field(default_factory=dict[str, Path])

    @property
    def name(self) -> str:
        return self.spec.name.text

    @property
    def parent(self) -> str | None:
        return self.spec.parent.text if self.spec.parent is not None else None


def split_qualified(name: str) -> tuple[str, str]:
    """``("S", "T")`` for a session-qualified name ``S.T``, else ``("", name)``.

    A name with a ``/`` is a path (``../Foo``, ``"Common/Bar"``), never qualified.
    """
    if "/" in name or "." not in name:
        return "", name
    qualifier, _, base = name.rpartition(".")
    return qualifier, base


def _read_roots_file(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def discover_roots(directory: Path) -> list[Path]:
    """ROOT files of a project directory.

    A directory with ``ROOT`` or ``ROOTS`` is read like ``isabelle build -D``:
    its own ``ROOT`` plus, recursively, every directory listed in ``ROOTS``.
    A directory with neither is searched recursively for ``ROOT`` files.
    """
    directory = directory.resolve()
    if not ((directory / "ROOT").is_file() or (directory / "ROOTS").is_file()):
        return sorted(
            p
            for p in directory.rglob("ROOT")
            if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(directory).parts)
        )
    found: list[Path] = []
    seen: set[Path] = set()
    stack = [directory]
    while stack:
        d = stack.pop()
        if d in seen:
            continue
        seen.add(d)
        if (d / "ROOT").is_file():
            found.append(d / "ROOT")
        if (d / "ROOTS").is_file():
            stack.extend(reversed([(d / e).resolve() for e in _read_roots_file(d / "ROOTS")]))
    return found


@dataclass
class Project:
    directory: Path
    roots: list[RootFile]
    sessions: dict[str, Session]
    problems: list[Problem]
    _headers: dict[Path, Header | None] = field(
        default_factory=dict[Path, Header | None], repr=False
    )
    _owners: dict[Path, Session] = field(default_factory=dict[Path, Session], repr=False)
    _declared_cache: dict[Path, dict[str, CommandKind]] = field(
        default_factory=dict[Path, dict[str, CommandKind]], repr=False
    )

    @classmethod
    def load(cls, directory: Path) -> "Project":
        roots = [read_root(p) for p in discover_roots(directory)]
        return cls.from_roots(directory.resolve(), roots)

    @classmethod
    def from_roots(cls, directory: Path, roots: list[RootFile]) -> "Project":
        problems: list[Problem] = []
        sessions: dict[str, Session] = {}
        for root in roots:
            assert root.path is not None
            problems += [_problem(root, d) for d in root.diagnostics]
            for spec in root.sessions:
                base = root.path.parent.resolve()
                session_dir = base / spec.dir.text if spec.dir is not None else base
                search = [session_dir] + [session_dir / d.text for d in spec.directories]
                if spec.name.text in sessions:
                    msg = f"duplicate session {spec.name.text}"
                    problems.append(_problem(root, Diagnostic(msg, spec.name.start)))
                    continue
                sessions[spec.name.text] = Session(spec, root, session_dir, search)
        project = cls(directory, roots, sessions, problems)
        project._resolve()
        return project

    # --- resolution -----------------------------------------------------------

    def header(self, path: Path) -> Header | None:
        if path not in self._headers:
            self._headers[path] = read_header(path)
        return self._headers[path]

    @staticmethod
    def _entry_file(session: Session, entry: str) -> Path | None:
        for d in session.search_dirs:
            candidate = d / f"{entry}.thy"
            if candidate.is_file():
                return candidate.resolve()
        return None

    def _session_theory(self, session_name: str, theory: str) -> Path | None:
        owner = self.sessions.get(session_name)
        if owner is None:
            return None
        return owner.theories.get(theory) or self._entry_file(owner, theory)

    def resolve_import(self, importer: Path, session: Session | None, name: str) -> Path | None:
        """The project file an import names; None if external or missing."""
        if name.startswith("~") or name.startswith("$"):
            return None  # relative to $ISABELLE_HOME or another root
        qualifier, base = split_qualified(name)
        if qualifier:
            return self._session_theory(qualifier, base)
        candidate = (importer.parent / f"{name}.thy").resolve()
        if candidate.is_file():
            return candidate
        if session is not None:
            return session.theories.get(Path(name).name) or self._entry_file(session, name)
        return None

    def _resolve(self) -> None:
        for session in self.sessions.values():
            for entry in session.spec.theories:
                text = entry.name.text
                if split_qualified(text)[0]:
                    continue  # another session's theory: checked below
                path = self._entry_file(session, text)
                if path is None:
                    self._entry_problem(
                        session,
                        entry.name,
                        f"theory entry {text!r} of session "
                        f"{session.name} has no .thy file on the session's search path",
                    )
                else:
                    session.theories[Path(text).name] = path
        # Imports pull further theories into the session that reaches them first.
        for session in self.sessions.values():
            for path in self.closure(list(session.theories.values()), session):
                owner = self._owners.setdefault(path, session)
                if owner is session:
                    session.theories.setdefault(path.stem, path)
        for session in self.sessions.values():
            for entry in session.spec.theories:
                qualifier, base = split_qualified(entry.name.text)
                if qualifier in self.sessions and self._session_theory(qualifier, base) is None:
                    self._entry_problem(
                        session,
                        entry.name,
                        f"theory entry {entry.name.text!r}: session "
                        f"{qualifier} has no theory {base}",
                    )

    def _entry_problem(self, session: Session, name: Name, message: str) -> None:
        self.problems.append(_problem(session.root, Diagnostic(message, name.start)))

    def closure(self, start: Iterable[Path], session: Session | None) -> Iterator[Path]:
        """``start`` and every project theory reachable through imports."""
        seen: set[Path] = set()
        stack = list(start)
        while stack:
            path = stack.pop()
            if path in seen:
                continue
            seen.add(path)
            yield path
            header = self.header(path)
            if header is None:
                continue
            owner = self._owners.get(path, session)
            for imp in header.imports:
                target = self.resolve_import(path, owner, imp.text)
                if target is not None:
                    stack.append(target)

    # --- queries --------------------------------------------------------------

    def session_of(self, path: Path) -> Session | None:
        return self._owners.get(path.resolve())

    def theory_files(self) -> list[Path]:
        """Every theory some session reaches, grouped by session."""
        return list(dict.fromkeys(p for s in self.sessions.values() for p in s.theories.values()))

    def unreached(self) -> list[tuple[Session, Path]]:
        """``.thy`` files on a session's search path that no session reaches.

        Files in the directory of another session (a nested ROOT) are skipped.
        """
        session_dirs = {s.dir for s in self.sessions.values()}
        found: list[tuple[Session, Path]] = []
        seen: set[Path] = set()
        for session in self.sessions.values():
            for d in session.search_dirs:
                if not d.is_dir():
                    continue
                for path in sorted(d.glob("*.thy")):
                    path = path.resolve()
                    if path in self._owners or path in seen:
                        continue
                    if path.parent in session_dirs and path.parent != session.dir:
                        continue
                    seen.add(path)
                    found.append((session, path))
        return found

    def keywords_for(self, path: Path) -> dict[str, CommandKind]:
        """Commands visible in ``path``: built-ins plus every command declared
        in its own header and in the headers of the project theories it
        imports, transitively."""
        return {**BUILTIN_COMMANDS, **self._declared(path.resolve(), frozenset())[0]}

    def _declared(self, path: Path, active: frozenset[Path]) -> tuple[dict[str, CommandKind], bool]:
        """Commands declared along ``path``'s imports, and whether the result is
        complete. It is not when an import cycle (an error in Isabelle) was cut;
        such a result is not cached."""
        if path in self._declared_cache:
            return self._declared_cache[path], True
        header = self.header(path)
        table: dict[str, CommandKind] = {}
        complete = True
        if header is not None:
            owner = self._owners.get(path)
            for imp in header.imports:
                target = self.resolve_import(path, owner, imp.text)
                if target is None:
                    continue
                if target in active or target == path:
                    complete = False
                    continue
                imported, imported_complete = self._declared(target, active | {path})
                table.update(imported)
                complete = complete and imported_complete
            table.update(keyword_table([header], builtin=False))
        if complete:
            self._declared_cache[path] = table
        return table, complete


def _problem(root: RootFile, diagnostic: Diagnostic) -> Problem:
    assert root.path is not None
    return Problem(root.path, root.lines.line(diagnostic.start), diagnostic.message)
