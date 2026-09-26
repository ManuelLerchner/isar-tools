"""``isar project``: sessions, theories, and their graph."""

import argparse
import json
import sys
from pathlib import Path

from isar_tools.project.model import Project, Session
from isar_tools.project.workspace import InputError, add_include_option
from isar_tools.render import RENDERERS, Cell, Column, Table, display_path


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:  # pyright: ignore[reportPrivateUsage]
    project = sub.add_parser(
        "project",
        help="Inspect Isabelle project structure",
        description="Inspect the sessions and theories of an Isabelle project.",
    )
    views = project.add_subparsers(dest="view", metavar="<view>", required=True)
    for name, summary in (
        ("sessions", "sessions with parent, directory, and theory count"),
        ("theories", "theories with their session and imports"),
    ):
        view = views.add_parser(name, help=summary, description=summary)
        view.add_argument("path", nargs="?", type=Path, default=Path(), help="project directory")
        view.add_argument("--format", choices=sorted(RENDERERS), default="text")
        add_include_option(view)
        view.set_defaults(func=run_table)
    graph = views.add_parser(
        "graph",
        help="the session graph, or with --theories the theory import graph",
        description="The session graph (parent and `sessions` edges), or with --theories "
        "the import graph of the project's theories.",
    )
    graph.add_argument("path", nargs="?", type=Path, default=Path(), help="project directory")
    graph.add_argument("--format", choices=("text", "json", "dot"), default="text")
    graph.add_argument("--theories", action="store_true", help="theory import graph")
    add_include_option(graph)
    graph.set_defaults(func=run_graph)


def _load(args: argparse.Namespace) -> Project:
    path: Path = args.path
    if not path.is_dir():
        raise InputError(f"{path}: not a directory")
    return Project.load(path, args.include)


def sessions_table(project: Project) -> Table:
    rows: list[dict[str, Cell]] = [
        {
            "session": s.name,
            "parent": s.parent or "",
            "chapter": s.spec.chapter,
            "theories": len(project.owned_theories(s)),
            "directory": display_path(s.dir),
            "root": display_path(s.root.path) if s.root.path is not None else "",
        }
        for s in project.own_sessions
    ]
    return Table(
        "sessions",
        "Sessions",
        [
            Column("session", "session"),
            Column("parent", "parent"),
            Column("chapter", "chapter"),
            Column("theories", "theories", True),
            Column("directory", "directory"),
            Column("root", "ROOT"),
        ],
        rows,
    )


def _imports(project: Project, session: Session, path: Path) -> list[str]:
    header = project.header(path)
    return [i.text for i in header.imports] if header is not None else []


def theories_table(project: Project) -> Table:
    rows: list[dict[str, Cell]] = []
    for session in project.own_sessions:
        for name, path in project.owned_theories(session).items():
            rows.append(
                {
                    "session": session.name,
                    "theory": name,
                    "imports": " ".join(_imports(project, session, path)),
                    "path": display_path(path),
                }
            )
    return Table(
        "theories",
        "Theories",
        [
            Column("session", "session"),
            Column("theory", "theory"),
            Column("imports", "imports"),
            Column("path", "path"),
        ],
        rows,
    )


def run_table(args: argparse.Namespace) -> int:
    project = _load(args)
    table = sessions_table(project) if args.view == "sessions" else theories_table(project)
    RENDERERS[args.format]([table], sys.stdout)
    return 0


def session_edges(project: Project) -> list[tuple[str, str, str]]:
    """(from, to, kind) with kind "parent" or "sessions"."""
    edges: list[tuple[str, str, str]] = []
    for s in project.own_sessions:
        if s.parent is not None:
            edges.append((s.name, s.parent, "parent"))
        edges += [(s.name, n.text, "sessions") for n in s.spec.sessions]
    return edges


def theory_edges(project: Project) -> list[tuple[str, str, str]]:
    """(importer, imported, "imports") between qualified names of project theories."""
    names: dict[Path, str] = {}
    for session in project.own_sessions:
        for name, path in project.owned_theories(session).items():
            names[path] = f"{session.name}.{name}"
    edges: list[tuple[str, str, str]] = []
    for path, name in names.items():
        session = project.session_of(path)
        header = project.header(path)
        assert header is not None
        assert session is not None
        for imp in header.imports:
            target = project.resolve_import(path, session, imp.text)
            edges.append((name, names.get(target, imp.text) if target else imp.text, "imports"))
    return edges


def _dot_id(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_graph(args: argparse.Namespace) -> int:
    project = _load(args)
    if args.theories:
        nodes = [f"{s.name}.{n}" for s in project.own_sessions for n in project.owned_theories(s)]
        edges = theory_edges(project)
    else:
        nodes = [s.name for s in project.own_sessions]
        edges = session_edges(project)
    if args.format == "json":
        json.dump(
            {"nodes": nodes, "edges": [{"from": a, "to": b, "kind": k} for a, b, k in edges]},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    elif args.format == "dot":
        print("digraph isabelle {")
        for node in nodes:
            print(f"  {_dot_id(node)};")
        for a, b, kind in edges:
            style = " [style=dashed]" if kind == "sessions" else ""
            print(f"  {_dot_id(a)} -> {_dot_id(b)}{style};")
        print("}")
    else:
        targets: dict[str, list[str]] = {}
        for a, b, kind in edges:
            targets.setdefault(a, []).append(b if kind != "sessions" else f"{b} (sessions)")
        for node in nodes:
            print(node)
            for target in targets.get(node, []):
                print(f"  -> {target}")
    return 0
