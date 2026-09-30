"""``isar project``: sessions, theories, their graph, and named declarations."""

import argparse
import json
import os
import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO, cast

from isar_tools.project.hierarchy import Located, as_json, closure, declarations, extends
from isar_tools.project.model import Project, Session
from isar_tools.project.names import (
    KINDS,
    Entity,
    Interpretation,
    entities,
    instances,
    interpretations,
    interpreted,
    matches,
    source,
)
from isar_tools.project.workspace import InputError, add_include_option, project_root
from isar_tools.render import RENDERERS, Cell, Column, Table, display_path
from isar_tools.source.files import read_source, write_source
from isar_tools.source.symbols import decode
from isar_tools.source.theory import Theory, parse_theory
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
        "exit 1 if a name declares nothing, suggesting the qualified names that exist. "
        "A theory file argument lists that file only, such as one of Isabelle's own.",
    )
    names.add_argument(
        "paths",
        nargs="*",
        type=Path,
        metavar="PATH",
        help="project directory, or theory file to read alone (default: .)",
    )
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
        "goal, its proof, dedented; with --statement, without the proof. NAME is "
        "`name`, `locale.name`, `Theory.name`, `Theory.locale.name`, `type :: class` for "
        "a class instance, or the qualifier of an interpretation, and must name exactly "
        "one declaration of the project. With --manifest, extract every entry "
        "of a TOML file into --out, one KEY.thy each, so quoted source cannot drift "
        "from the theories.",
    )
    extract.add_argument("names", nargs="*", metavar="NAME")
    extract.add_argument(
        "--project", type=Path, default=Path(), metavar="DIR", help="project directory"
    )
    extract.add_argument(
        "--statement",
        action="store_true",
        help="only the statement: without the proof of a goal, and without the `begin` "
        "of a locale, class, or instantiation",
    )
    extract.add_argument(
        "--manifest",
        type=Path,
        metavar="TOML",
        help="what to extract: a table [snippets.KEY] per snippet, written to KEY.thy, "
        "with optional `name` (the NAME to extract; default KEY), `file` (theory path "
        "relative to the project) to choose between declarations, and `proof` (true or "
        "false, overriding --statement)",
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


@dataclass(frozen=True)
class _Found:
    entity: Entity
    theory: Theory | None  # None for a fact an interpretation makes
    session: str  # "" for a theory of no known session
    external: bool = False  # from a -d directory or a file outside every session


_Interpretation = tuple[Interpretation, str]  # and the session of its theory


def _theory_entities(
    project: Project | None, path: Path, derived: bool, named: bool, session: str, external: bool
) -> tuple[list[_Found], list[_Interpretation]]:
    """The declarations of one theory file, and its qualified interpretations
    if ``derived``. Without a ``project``, the file is read on its own."""
    keywords = project.keywords_for(path) if project is not None else None
    theory = parse_theory(read_source(path), keywords)
    name = path.stem

    def found(e: Entity) -> _Found:
        return _Found(e, theory, session, external)

    result = [found(e) for e in entities(theory, name, path, derived)]
    if named:
        result += [found(i.entity) for i in instances(theory, name, path) if i.entity.name]
    interps = interpretations(theory, name, path) if derived else ()
    return result, [(i, session) for i in interps]


def _with_interpretations(found: list[_Found], interps: list[_Interpretation]) -> list[_Found]:
    """``found`` and the facts ``interps`` make of its facts."""
    facts = [f.entity for f in found]
    return found + [_Found(e, None, s) for i, s in interps for e in interpreted(facts, i)]


def _entities(
    project: Project, derived: bool = False, named: bool = False, external: bool = False
) -> list[_Found]:
    """Declarations of the project's theories. With ``derived``, also derived
    facts and those of qualified interpretations; with ``named``, also class
    instances (``t :: c``) and qualified interpretations (by the qualifier);
    with ``external``, also the theories of -d directories."""
    found: list[_Found] = []
    interps: list[_Interpretation] = []
    for session in project.sessions.values():
        if session.external and not external:
            continue
        for path in project.owned_theories(session).values():
            more, made = _theory_entities(
                project, path, derived, named, session.name, session.external
            )
            found += more
            interps += made
    return _with_interpretations(found, interps)


def _lookup(found: list[_Found], name: str, file: Path | None) -> _Found | str:
    """The one declaration ``name`` refers to, or why there is none. The
    project's declarations hide those of -d directories, and a declaration
    hides the parameters, fields, and constructors other declarations have of
    the same name."""
    if "::" in name:  # an instance, spelt `t :: c`
        name = " :: ".join(part.strip() for part in name.split("::"))
    hits = [f for f in found if matches(f.entity, name)]
    if file is not None:
        hits = [f for f in hits if f.entity.path == file.resolve()]
    hits = [f for f in hits if not f.external] or hits
    # A declaration and its members, like a class and its parameter, are one source.
    by_extent: dict[tuple[Path, int, int], _Found] = {}
    for f in sorted(hits, key=lambda f: f.entity.member):
        by_extent.setdefault((f.entity.path, f.entity.start, f.entity.end), f)
    hits = list(by_extent.values())
    hits = [f for f in hits if not f.entity.member] or hits
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return f"{name}: no declaration" + (f" in {_display(file)}" if file else "")
    where = ", ".join(
        f"{f.entity.qualified} ({_display(f.entity.path)}:{f.entity.line})" for f in hits
    )
    return f"{name}: ambiguous: {where}"


_Source = tuple[Entity, str]  # a declaration and the source text extracted

# How Isabelle writes its own directory, ISABELLE_HOME.
_ISABELLE_PREFIX = "~~/"


def _isabelle_home() -> Path | None:
    home = os.environ.get("ISABELLE_HOME")
    return Path(home).resolve() if home else None


def _display(path: Path) -> str:
    """``path`` for a reader; below ISABELLE_HOME as ``~~/...``."""
    home = _isabelle_home()
    if home is not None and path.resolve().is_relative_to(home):
        return _ISABELLE_PREFIX + path.resolve().relative_to(home).as_posix()
    return display_path(path)


def _snippet(entity: Entity, text: str) -> str:
    return f"(* {_display(entity.path)} *)\n{text}"


@dataclass(frozen=True)
class _Wanted:
    """A declaration to extract."""

    name: str
    file: Path | None  # the theory file it is pinned to
    proof: bool | None  # with or without its proof; None: as --statement says


def _entry(key: str, meta: object, project: Path) -> _Wanted | str:
    """A manifest entry, or why it is skipped."""
    fields = cast(dict[str, object], meta) if isinstance(meta, dict) else {}
    name, file, proof = fields.get("name"), fields.get("file"), fields.get("proof")
    path: Path | None = None
    if isinstance(file, str) and file.startswith(_ISABELLE_PREFIX):
        home = _isabelle_home()
        if home is None:
            return f"skipped {key}: {file} needs ISABELLE_HOME"
        path = home / file.removeprefix(_ISABELLE_PREFIX)
    elif isinstance(file, str):
        path = project / file
    return _Wanted(
        name if isinstance(name, str) else key, path, proof if isinstance(proof, bool) else None
    )


def _manifest(path: Path, project: Path) -> dict[str, _Wanted]:
    """The entries of a manifest, by key. An entry pinned to Isabelle's own
    sources is skipped, with a note, when ISABELLE_HOME is not set."""
    try:
        table = tomllib.loads(read_source(path)).get("snippets", {})
    except (OSError, ValueError) as err:  # TOMLDecodeError and UnicodeDecodeError
        raise InputError(f"{path.as_posix()}: {err}") from err
    if not isinstance(table, dict):
        raise InputError(f"{path.as_posix()}: [snippets] must be a table")
    wanted: dict[str, _Wanted] = {}
    for key, meta in sorted(cast(dict[str, object], table).items()):
        entry = _entry(key, meta, project)
        if isinstance(entry, str):
            print(f"isar project extract: note: {entry}", file=sys.stderr)
        else:
            wanted[key] = entry
    return wanted


def _pinned(project: Project, files: Iterable[Path | None]) -> list[_Found]:
    """Declarations of pinned theory files that no session of the project or
    of a -d directory owns, such as Isabelle's own theories, each read on its
    own."""
    found: list[_Found] = []
    for path in dict.fromkeys(f.resolve() for f in files if f is not None):
        if project.session_of(path) is None and path.is_file():
            found += _theory_entities(None, path, False, True, "", True)[0]
    return found


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
        else {name: _Wanted(name, None, None) for name in args.names}
    )
    project = _load_dir(args.project, args.include)
    found = _entities(project, named=True, external=True)
    found += _pinned(project, (w.file for w in wanted.values()))
    ok: dict[str, _Source] = {}
    errors = 0
    for key, want in wanted.items():
        result = _lookup(found, want.name, want.file)
        if isinstance(result, str):
            errors += 1
            print(f"isar project extract: {result}", file=sys.stderr)
            continue
        entity, theory = result.entity, result.theory
        assert theory is not None  # interpretation facts are not looked up
        statement = args.statement if want.proof is None else not want.proof
        ok[key] = (entity, source(theory, entity, statement))
    if args.manifest is None:
        if args.format == "json":
            rows = [
                {
                    "name": name,
                    "qualified": e.qualified,
                    "kind": e.kind,
                    "command": e.command,
                    "path": _display(e.path),
                    "line": e.line,
                    # The source runs from the start of the first line to the last token.
                    "end_line": e.line + text.count("\n") - 1,
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


def _sync(args: argparse.Namespace, ok: dict[str, _Source]) -> int:
    """Write or compare the manifest's snippets; 1 if ``--check`` finds drift."""
    out: Path = args.out
    style = Style.for_stream(args.color, sys.stdout)
    stale = 0
    for key, (entity, text) in ok.items():
        target = out / f"{key}.thy"
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


def names_table(found: list[_Found], docs: bool, derived: bool = False) -> Table:
    rows: list[dict[str, Cell]] = []
    for f in found:
        e = f.entity
        rows.append(
            {
                "name": e.qualified,
                "kind": e.kind,
                "command": e.command,
                "session": f.session,
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


def write_index(found: list[_Found], out: TextIO) -> None:
    out.write("# Declarations\n")
    session_name = ""
    path: Path | None = None
    for f in found:
        e, name = f.entity, f.session
        if name != session_name or path is None:
            session_name = name
            out.write(f"\n## Session {name}\n")
        if e.path != path:
            path = e.path
            out.write(f"\n### {e.theory} (`{display_path(e.path)}`)\n\n")
            out.write("| Name | Kind | Line | Description |\n| --- | --- | ---: | --- |\n")
        local = f"{e.scope}.{e.name}" if e.scope else e.name
        out.write(f"| `{decode(local)}` | {e.command} | {e.line} | {_prose(e.doc)} |\n")


def _named(paths: list[Path], include: list[Path], derived: bool) -> list[_Found]:
    """Declarations of the projects in the directories of ``paths`` and of
    the theory files among them, each file read with the project it is in."""
    found: list[_Found] = []
    interps: list[_Interpretation] = []
    for path in paths:
        if path.is_dir():
            found += _entities(_load_dir(path, include), derived)
        elif path.is_file() and path.suffix == ".thy":
            project = Project.load(project_root(path), include)
            session = project.session_of(path)
            name = session.name if session is not None else ""
            more, made = _theory_entities(project, path.resolve(), derived, False, name, False)
            found += more
            interps += made
        else:
            raise InputError(f"{path.as_posix()}: not a directory or .thy file")
    return _with_interpretations(found, interps)


def run_names(args: argparse.Namespace) -> int:
    found = _named(list(dict.fromkeys(args.paths)) or [Path()], args.include, args.derived)
    if args.kind:
        found = [f for f in found if f.entity.kind in args.kind]
    missing = 0
    if args.name:
        for name in args.name:
            if any(_qualified_hit(f.entity, name) for f in found):
                continue
            missing += 1
            base = name.rpartition(".")[2]
            near = sorted({f.entity.qualified for f in found if f.entity.name == base})
            hint = f"; did you mean {', '.join(near)}?" if near else ""
            print(f"isar project names: {name}: no declaration{hint}", file=sys.stderr)
        found = [f for f in found if any(_qualified_hit(f.entity, n) for n in args.name)]
    if args.format == "markdown":
        write_index(found, sys.stdout)
    else:
        # Docstrings span lines, which a text table cannot show.
        table = names_table(found, docs=args.format != "text", derived=args.derived)
        RENDERERS[args.format]([table], sys.stdout)
    return 1 if missing else 0
