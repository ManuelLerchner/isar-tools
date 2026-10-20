"""Which declarations cite which: the reference graph of a project's theories.

Read from the source, as ``isar check unused`` reads it. A declaration cites
another when its text names it, or one of the facts it derives (``f_def``,
``f.simps``), and the cited one's theory is among those the citing theory
imports. A declaration of a locale or class (a lemma in it, an ``assumes``,
a ``fixes``) is cited without its scope (``x``, not ``L.x``) only from that
locale or class or one extending it. What a method finds by itself, such as
a ``[simp]`` rule, is no citation, and neither are the facts an
interpretation makes (``q.fact``).
"""

from bisect import bisect_right
from pathlib import Path

from isar_tools.checks.unused import uses
from isar_tools.project.hierarchy import Located, declarations, extends
from isar_tools.project.model import Project
from isar_tools.project.names import Entity, entities, spellings
from isar_tools.source.files import read_lenient
from isar_tools.source.theory import parse_theory


def _scope(name: str) -> str:
    """A class's members have the scope ``c_class``, its lemmas ``c``."""
    return name.removesuffix("_class")


class References:
    """The citations among the declarations of a project's theories and of
    its -d directories."""

    def __init__(self, project: Project) -> None:
        self._project = project
        self._reach: dict[Path, frozenset[Path]] = {}
        self._parents: dict[str, set[str]] = {}
        self._ancestors: dict[str, frozenset[str]] = {}
        self.cites: dict[Entity, set[Entity]] = {}
        self.cited_by: dict[Entity, set[Entity]] = {}
        named: dict[str, list[Entity]] = {}
        read: list[tuple[Path, list[Entity], list[tuple[str, int]]]] = []
        for session in project.sessions.values():
            for path in project.owned_theories(session).values():
                theory = parse_theory(read_lenient(path), project.keywords_for(path))
                found = list(entities(theory, path.stem, path, derived=True))
                origins = {e.qualified: e for e in found if not e.derived_from}
                for e in found:
                    origin = origins.get(e.derived_from, e)
                    for name in spellings(e):
                        named.setdefault(name, []).append(origin)
                for decl in declarations(theory, path):
                    parents = {
                        _scope(p.rpartition(".")[2]) for p in extends(Located(decl, "", False))
                    }
                    self._parents.setdefault(decl.name, set()).update(parents)
                owners = [e for e in found if not e.derived_from and not e.member]
                read.append((path, sorted(owners, key=lambda e: e.start), list(uses(theory))))
        for path, owners, used in read:
            self._cite(path, owners, named, used)

    def _cite(
        self,
        path: Path,
        declared: list[Entity],
        named: dict[str, list[Entity]],
        used: list[tuple[str, int]],
    ) -> None:
        # Extents of declarations are disjoint or, for one command declaring
        # several names, equal: group them by extent.
        groups: dict[int, list[Entity]] = {}
        for e in declared:
            groups.setdefault(e.start, []).append(e)
        starts = list(groups)
        reach = self.reach(path)
        for name, offset in used:
            k = bisect_right(starts, offset)
            owners = groups[starts[k - 1]] if k else []
            # The name a command declares is no citation of an imported namesake.
            if not owners or offset >= owners[0].end or any(name == o.name for o in owners):
                continue
            first = owners[0]
            # Within its own theory, a name means what an earlier command
            # declared, which shadows the imported ones: the members of a
            # locale do not cite the locale.
            candidates = [
                c
                for c in named.get(name, ())
                if c.path in reach
                and (c.path != path or c.start < first.start)
                and self._in_scope(c, name, first)
            ]
            for cited in [c for c in candidates if c.path == path] or candidates:
                for owner in owners:
                    self.cites.setdefault(owner, set()).add(cited)
                    self.cited_by.setdefault(cited, set()).add(owner)

    def _in_scope(self, cited: Entity, name: str, owner: Entity) -> bool:
        """Whether ``name``, written in ``owner``, can mean ``cited``."""
        if not cited.scope or cited.scope in name.split(".")[:-1]:
            return True
        where = owner.scope or (owner.name if owner.kind in ("locale", "class") else "")
        return _scope(cited.scope) in self.ancestors(_scope(where))

    def ancestors(self, scope: str) -> frozenset[str]:
        """``scope`` and every locale or class it extends, transitively; empty
        for no scope."""
        if not scope:
            return frozenset()
        if scope not in self._ancestors:
            self._ancestors[scope] = frozenset({scope})  # cuts a (malformed) cycle
            parents = self._parents.get(scope, set())
            self._ancestors[scope] = frozenset({scope}).union(*map(self.ancestors, parents))
        return self._ancestors[scope]

    def reach(self, path: Path) -> frozenset[Path]:
        """``path`` and every theory of the project it imports, transitively."""
        if path not in self._reach:
            session = self._project.session_of(path)
            self._reach[path] = frozenset(self._project.closure([path], session))
        return self._reach[path]


def walk(
    edges: dict[Entity, set[Entity]], start: Entity, transitive: bool
) -> list[tuple[Entity, int]]:
    """The declarations ``edges`` lead to from ``start``, each with its distance:
    with ``transitive`` every one reachable, else the direct ones. Nearest
    first, then in source order."""
    seen = {start}
    frontier = {start}
    found: dict[Entity, int] = {}
    depth = 0
    while frontier and (transitive or depth == 0):
        depth += 1
        frontier = {e for f in frontier for e in edges.get(f, ()) if e not in seen}
        seen |= frontier
        found.update(dict.fromkeys(frontier, depth))
    return sorted(
        found.items(), key=lambda item: (item[1], item[0].path, item[0].start, item[0].name)
    )
