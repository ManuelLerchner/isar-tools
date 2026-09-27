"""Project checks: ROOT files, sessions, and which theory files get built."""

from collections import defaultdict
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.project.model import Project, Session
from isar_tools.project.root import RootFile
from isar_tools.source.theory import Name


def _at(root: RootFile, name: Name, code: str, message: str) -> Finding:
    assert root.path is not None
    return Finding.at(root.path, root.lines, name.start, code, message)


def _directories(session: Session) -> list[Finding]:
    findings: list[Finding] = []
    spec, root = session.spec, session.root
    if spec.dir is not None and not session.dir.is_dir():
        findings.append(
            _at(
                root,
                spec.dir,
                "missing-directory",
                f"no directory {spec.dir.text} for session {session.name}",
            )
        )
    for name in spec.directories:
        if not (session.dir / name.text).is_dir():
            findings.append(
                _at(
                    root,
                    name,
                    "missing-directory",
                    f"no directory {name.text} for session {session.name}",
                )
            )
    for directory, name in spec.document_files:
        if directory.startswith(("$", "~")):
            continue  # relative to an Isabelle setting, unknown here
        if not (session.dir / directory / name.text).is_file():
            findings.append(
                _at(
                    root,
                    name,
                    "missing-document-file",
                    f"no document file {directory}/{name.text} for session {session.name}",
                )
            )
    return findings


def _duplicate_names(project: Project, session: Session) -> list[Finding]:
    """Two files with one stem on one search path: Isabelle builds one and
    silently ignores the other."""
    session_dirs = {s.dir for s in project.sessions.values()}
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for d in dict.fromkeys(session.search_dirs):
        if not d.is_dir() or (d in session_dirs and d != session.dir):
            continue
        for path in sorted(d.glob("*.thy")):
            by_stem[path.stem].append(path.resolve())
    findings: list[Finding] = []
    for stem, paths in sorted(by_stem.items()):
        if len(paths) > 1:
            where = ", ".join(p.relative_to(session.dir).as_posix() for p in paths)
            assert session.root.path is not None
            findings.append(
                Finding(
                    session.root.path,
                    session.root.lines.line(session.spec.name.start),
                    session.root.lines.column(session.spec.name.start),
                    "duplicate-theory-name",
                    f"two theories {stem} on the search path of session {session.name} "
                    f"({where}); only one is built",
                )
            )
    return findings


def check_project(project: Project) -> list[Finding]:
    findings = [Finding(p.path, p.line, p.column, p.code, p.message) for p in project.problems]
    for session in project.own_sessions:
        findings += _directories(session)
        findings += _duplicate_names(project, session)
    for session, path in project.unreached():
        findings.append(
            Finding(
                path,
                1,
                1,
                "unreached-theory",
                f"not built by any session (on the search path of {session.name})",
            )
        )
    return findings
