"""``isar project``: sessions, theories, their graph, and named declarations."""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import TextIO, cast

from isar_tools.project.hierarchy import Located, as_json, closure, declarations, extends
from isar_tools.project.model import Project, Session
from isar_tools.project.names import (
    KINDS,
    Entity,
    Interpretation,
    entities,
    interpretations,
    interpreted,
    matches,
    source,
)
from isar_tools.project.workspace import InputError, add_include_option
from isar_tools.render import RENDERERS, Cell, Column, Table, display_path
from isar_tools.source.files import read_source, write_source
from isar_tools.source.symbols import decode
from isar_tools.source.theory import parse_theory
from isar_tools.style import Style, add_color_option, write_diff


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
    hierarchy = views.add_parser(
        "hierarchy",
        help="class and locale declarations: parents, parameters, assumptions",
        description="Class and locale declarations read from the sources: parents, "
        "fixes with type and notation, assumes, and parameter sorts. With --root, only "
        "the named declarations and everything they extend, parents first, including "
        "declarations in -d directories.",
    )
    hierarchy.add_argument("path", nargs="?", type=Path, default=Path(), help="project directory")
    hierarchy.add_argument(
        "--root", action="append", default=[], metavar="NAME", help="start here (repeatable)"
    )
    hierarchy.add_argument("--format", choices=("text", "json", "dot"), default="text")
    add_include_option(hierarchy)
    hierarchy.set_defaults(func=run_hierarchy)
    names = views.add_parser(
        "names",
        help="named declarations with kind, location, and docstring",
        description="Facts, constants, types, locales, classes, and bundles the project's "
        "theories declare, with qualified names as Isabelle renders them "
        "(Theory.locale.name) and the text block directly before each as its docstring. "
        "--format markdown writes an index grouped by session and theory. With --name, "
        "exit 1 if a name declares nothing, suggesting the qualified names that exist.",
    )
    names.add_argument("path", nargs="?", type=Path, default=Path(), help="project directory")
    names.add_argument(
        "--kind",
        action="append",
        choices=sorted(set(KINDS.values())),
        help="only this kind (repeatable)",
    )
    names.add_argument(
        "--name",
        action="append",
        default=[],
        metavar="NAME",
        help="only NAME, a base name or an exact qualified name (repeatable)",
    )
    names.add_argument(
        "--derived",
        action="store_true",
        help="also list derived facts (f_def, f.simps, the rules of an inductive, L.intro, "
        "...) and the facts of qualified interpretations (q.fact)",
    )
    names.add_argument("--format", choices=sorted(RENDERERS), default="text")
    add_include_option(names)
    names.set_defaults(func=run_names)
    extract = views.add_parser(
        "extract",
        help="the source of declarations, by name",
        description="Print the source of named declarations: the command and, for a "
        "goal, its proof, dedented. NAME is `name`, `locale.name`, `Theory.name`, or "
        "`Theory.locale.name`, and must name exactly one declaration of the project. "
        "With --manifest, extract every name listed in a TOML file into --out, one "
        "NAME.thy each, so quoted source cannot drift from the theories.",
    )
    extract.add_argument("names", nargs="*", metavar="NAME")
    extract.add_argument(
        "--project", type=Path, default=Path(), metavar="DIR", help="project directory"
    )
    extract.add_argument(
        "--manifest",
        type=Path,
        metavar="TOML",
        help="names to extract: a table [snippets.NAME] per name, with an optional "
        "`file` (theory path relative to the project) to choose between declarations",
    )
    extract.add_argument("--out", type=Path, metavar="DIR", help="directory for --manifest")
    mode = extract.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write --out (with --manifest)")
    mode.add_argument(
        "--check", action="store_true", help="exit 1 if --out differs (with --manifest)"
    )
    extract.add_argument("--format", choices=("text", "json"), default="text")
    add_include_option(extract)
    add_color_option(extract)
    extract.set_defaults(func=run_extract)


def _load(args: argparse.Namespace) -> Project:
    return _load_dir(args.path, args.include)


def _load_dir(path: Path, include: list[Path]) -> Project:
    if not path.is_dir():
        raise InputError(f"{path.as_posix()}: not a directory")
    return Project.load(path, include)


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


def _declaration_index(project: Project, external: bool) -> dict[str, list[Located]]:
    """Declarations by name: the project's, and with ``external`` those of the
    included sessions too."""
    index: dict[str, list[Located]] = {}
    for session in project.sessions.values():
        if session.external and not external:
            continue
        for path in project.owned_theories(session).values():
            text = read_source(path)
            if "class" not in text and "locale" not in text:
                continue  # cheap filter before parsing
            theory = parse_theory(text, project.keywords_for(path))
            for decl in declarations(theory, path):
                located = Located(decl, session.name, session.external)
                index.setdefault(decl.name, []).append(located)
    return index


def run_hierarchy(args: argparse.Namespace) -> int:
    project = _load(args)
    index = _declaration_index(project, external=bool(args.root))
    if args.root:
        cache: dict[Path, set[Path]] = {}

        def visible(path: Path) -> set[Path]:
            if path not in cache:
                cache[path] = set(project.closure([path], project.session_of(path)))
            return cache[path]

        found, missing = closure(index, args.root, visible)
    else:
        found = sorted(
            (loc for locs in index.values() for loc in locs),
            key=lambda loc: (loc.decl.path, loc.decl.line),
        )
        missing = []
    for name in missing:
        print(f"isar project hierarchy: warning: no class or locale {name}", file=sys.stderr)
    names = {loc.decl.name for loc in found}
    if args.format == "json":
        json.dump(
            {
                "declarations": [as_json(loc, display_path(loc.decl.path)) for loc in found],
                "unresolved": missing,
            },
            sys.stdout,
            indent=2,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
    elif args.format == "dot":
        print("digraph hierarchy {")
        print("  node [shape=box];")
        for loc in found:
            style = ", style=dashed" if loc.decl.kind == "locale" else ""
            print(f"  {_dot_id(loc.decl.name)} [label={_dot_id(loc.decl.name)}{style}];")
        for loc in found:
            decl = loc.decl
            for parent in extends(loc):
                if parent in names:
                    print(f"  {_dot_id(decl.name)} -> {_dot_id(parent)} [arrowhead=empty];")
            if decl.kind == "locale":
                for sort in decl.sorts:
                    if sort in names:
                        print(f"  {_dot_id(decl.name)} -> {_dot_id(sort)} [style=dashed];")
        print("}")
    else:
        for loc in found:
            decl = loc.decl
            where = f"{display_path(decl.path)}:{decl.line}"
            print(f"{decl.kind} {decl.name}  ({loc.session}, {where})")
            if decl.parents:
                print(f"  extends {' + '.join(decl.parents)}")
            if decl.sorts:
                print(f"  sorts   {', '.join(decl.sorts)}")
            for p in decl.fixes:
                notation = f"  ({p.mixfix})" if p.mixfix else ""
                typed = f" :: {p.type}" if p.type else ""
                print(f"  fixes   {p.name}{typed}{notation}")
            for a in decl.assumes:
                label = f"{a.name}: " if a.name else ""
                print(f"  assumes {label}{' '.join(a.props)}")
    return 0


_Found = tuple[Entity, str]  # an entity and its source text


def _entities(project: Project, derived: bool = False) -> list[_Found]:
    """Declarations of the project's theories, with their source. With
    ``derived``, also derived facts and those of qualified interpretations."""
    found: list[_Found] = []
    interps: list[Interpretation] = []
    for session in project.own_sessions:
        for name, path in project.owned_theories(session).items():
            theory = parse_theory(read_source(path), project.keywords_for(path))
            found += [(e, source(theory, e)) for e in entities(theory, name, path, derived)]
            if derived:
                interps += interpretations(theory, name, path)
    facts = [e for e, _ in found]
    for interp in interps:
        found += [(e, "") for e in interpreted(facts, interp)]
    return found


def _lookup(found: list[_Found], name: str, file: Path | None) -> _Found | str:
    """The one declaration ``name`` refers to, or why there is none."""
    hits = [f for f in found if matches(f[0], name)]
    if file is not None:
        hits = [f for f in hits if f[0].path == file.resolve()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return f"{name}: no declaration" + (f" in {file.as_posix()}" if file else "")
    where = ", ".join(f"{e.qualified} ({display_path(e.path)}:{e.line})" for e, _ in hits)
    return f"{name}: ambiguous: {where}"


def _snippet(entity: Entity, text: str) -> str:
    return f"(* {display_path(entity.path)} *)\n{text}"


def _manifest(path: Path, project: Path) -> dict[str, Path | None]:
    """Names listed in a manifest, each with the theory file it is pinned to."""
    try:
        table = tomllib.loads(read_source(path)).get("snippets", {})
    except (OSError, ValueError) as err:  # TOMLDecodeError and UnicodeDecodeError
        raise InputError(f"{path.as_posix()}: {err}") from err
    if not isinstance(table, dict):
        raise InputError(f"{path.as_posix()}: [snippets] must be a table")
    wanted: dict[str, Path | None] = {}
    for name, meta in sorted(cast(dict[str, object], table).items()):
        file = cast(dict[str, object], meta).get("file") if isinstance(meta, dict) else None
        wanted[name] = project / file if isinstance(file, str) else None
    return wanted


def run_extract(args: argparse.Namespace) -> int:
    if args.manifest is None and (args.out or args.write or args.check):
        raise InputError("--out, --write, and --check need --manifest")
    if args.manifest is not None and (args.names or args.out is None):
        raise InputError("--manifest takes no NAME and needs --out")
    if args.manifest is not None and not (args.write or args.check):
        raise InputError("--manifest needs --write or --check")
    if args.manifest is None and not args.names:
        raise InputError("give a NAME or --manifest")
    wanted = (
        _manifest(args.manifest, args.project)
        if args.manifest is not None
        else dict.fromkeys(args.names)
    )
    found = _entities(_load_dir(args.project, args.include))
    results = {name: _lookup(found, name, file) for name, file in wanted.items()}
    errors = [r for r in results.values() if isinstance(r, str)]
    for error in errors:
        print(f"isar project extract: {error}", file=sys.stderr)
    ok = {name: r for name, r in results.items() if not isinstance(r, str)}
    if args.manifest is None:
        if args.format == "json":
            rows = [
                {
                    "name": name,
                    "qualified": e.qualified,
                    "kind": e.kind,
                    "command": e.command,
                    "path": display_path(e.path),
                    "line": e.line,
                    "end_line": e.end_line,
                    "source": text,
                }
                for name, (e, text) in ok.items()
            ]
            json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")
        else:
            sys.stdout.write("\n".join(_snippet(e, text) for e, text in ok.values()))
        return 1 if errors else 0
    return _sync(args, ok) or (1 if errors else 0)


def _sync(args: argparse.Namespace, ok: dict[str, _Found]) -> int:
    """Write or compare the manifest's snippets; 1 if ``--check`` finds drift."""
    out: Path = args.out
    style = Style.for_stream(args.color, sys.stdout)
    stale = 0
    for name, (entity, text) in ok.items():
        target = out / f"{name}.thy"
        snippet = _snippet(entity, text)
        stored = read_source(target) if target.is_file() else ""
        if stored == snippet:
            continue
        if args.check:
            stale += 1
            write_diff(stored, snippet, display_path(target), sys.stdout, style)
        else:
            out.mkdir(parents=True, exist_ok=True)
            write_source(target, snippet)
            print(f"wrote {display_path(target)}")
    if stale and args.check:
        print(f"{stale} snippet(s) differ from the theories", file=sys.stderr)
    return 1 if stale and args.check else 0


def _qualified_hit(entity: Entity, name: str) -> bool:
    """``name`` is the entity's base name or its exact qualified name: a
    qualifier naming the wrong scope does not match."""
    return name in (entity.name, entity.qualified)


def names_table(project: Project, found: list[Entity], docs: bool, derived: bool = False) -> Table:
    rows: list[dict[str, Cell]] = []
    for e in found:
        session = project.session_of(e.path)
        rows.append(
            {
                "name": e.qualified,
                "kind": e.kind,
                "command": e.command,
                "session": session.name if session is not None else "",
                "path": display_path(e.path),
                "line": e.line,
                "end_line": e.end_line,
                "doc": e.doc,
                "derived_from": e.derived_from,
            }
        )
    return Table(
        "names",
        "Declarations",
        [
            Column("name", "name"),
            Column("kind", "kind"),
            Column("command", "command"),
            Column("session", "session"),
            Column("path", "path"),
            Column("line", "line", True),
            Column("end_line", "end", True),
            *([Column("derived_from", "from")] if derived else []),
            *([Column("doc", "doc")] if docs else []),
        ],
        rows,
    )


_ANTIQUOTATION = re.compile(r"\\<\^\w+>(\\<open>|‹)(.*?)(\\<close>|›)|@\{\w+\s+([^}]*)\}")
_CARTOUCHE = re.compile(r"(?:\\<open>|‹)(.*?)(?:\\<close>|›)")


def _prose(doc: str) -> str:
    """A docstring as one Markdown table cell: antiquotations and cartouches
    as code, symbols as Unicode."""
    text = _ANTIQUOTATION.sub(lambda m: f"`{(m.group(2) or m.group(4)).strip()}`", doc)
    text = _CARTOUCHE.sub(lambda m: f"`{m.group(1).strip()}`", text)
    return " ".join(decode(text).split()).replace("|", "\\|")


def write_index(project: Project, found: list[Entity], out: TextIO) -> None:
    out.write("# Declarations\n")
    session_name = ""
    path: Path | None = None
    for e in found:
        session = project.session_of(e.path)
        name = session.name if session is not None else ""
        if name != session_name or path is None:
            session_name = name
            out.write(f"\n## Session {name}\n")
        if e.path != path:
            path = e.path
            out.write(f"\n### {e.theory} (`{display_path(e.path)}`)\n\n")
            out.write("| Name | Kind | Line | Description |\n| --- | --- | ---: | --- |\n")
        local = f"{e.scope}.{e.name}" if e.scope else e.name
        out.write(f"| `{decode(local)}` | {e.command} | {e.line} | {_prose(e.doc)} |\n")


def run_names(args: argparse.Namespace) -> int:
    project = _load(args)
    found = [e for e, _ in _entities(project, args.derived)]
    if args.kind:
        found = [e for e in found if e.kind in args.kind]
    missing = 0
    if args.name:
        for name in args.name:
            if any(_qualified_hit(e, name) for e in found):
                continue
            missing += 1
            base = name.rpartition(".")[2]
            near = sorted({e.qualified for e in found if e.name == base})
            hint = f"; did you mean {', '.join(near)}?" if near else ""
            print(f"isar project names: {name}: no declaration{hint}", file=sys.stderr)
        found = [e for e in found if any(_qualified_hit(e, n) for n in args.name)]
    if args.format == "markdown":
        write_index(project, found, sys.stdout)
    else:
        # Docstrings span lines, which a text table cannot show.
        table = names_table(project, found, docs=args.format != "text", derived=args.derived)
        RENDERERS[args.format]([table], sys.stdout)
    return 1 if missing else 0
