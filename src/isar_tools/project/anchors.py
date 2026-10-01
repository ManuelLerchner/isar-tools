"""The anchors of a built HTML presentation, found by name.

Isabelle's HTML presentation (``browser_info``) gives each definition an id,
``Theory.loc.name|kind``, on ``Chapter/Session/Theory.html``. The sources of a
project give its own anchors (``project names``); the build also has those of
HOL and every library session it rendered. A session that elaborates another
session's theory renders a copy, ``Owner.Theory.html``, which is skipped so a
name resolves to its owner's page.

A name is found by any dotted suffix of its id (``loc.name``, ``name``) and,
only if no suffix matches, as ``Theory.name`` for a member of a locale, class,
or type. Ids of one definition count once: a lemma's ``fact`` and ``thm``, and
a class's ``T.c.x`` and ``T.c_class.x``. When several definitions match, the
lookup returns all of them: ``prefer`` (prefixes of the page path, first is
best) narrows them, and the caller reports what remains instead of picking one.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from isar_tools.checks.links import ANCHOR_ID, Pages
from isar_tools.project.names import ANCHOR_SAFE

# Which anchor of one definition a lookup without a kind returns: a lemma has
# both `fact` and `thm`, a class both `locale` and `class`.
KIND_ORDER = ("fact", "thm", "locale", "class", "const", "type")


@dataclass(frozen=True)
class Anchor:
    name: str  # as in the id, symbols unescaped: Theory.loc.name
    kind: str
    page: str  # below browser_info, with `/`

    @property
    def id(self) -> str:
        return f"{self.name}|{self.kind}"

    @property
    def url(self) -> str:
        return f"{self.page}#{quote(self.id, safe=ANCHOR_SAFE)}"


def read_anchors(browser_info: Path) -> list[Anchor]:
    """Every anchor of the theory pages below ``browser_info``."""
    pages = Pages()
    found: list[Anchor] = []
    pages_by_name = {
        p.relative_to(browser_info).as_posix(): p for p in browser_info.rglob("*.html")
    }
    for page, path in sorted(pages_by_name.items()):
        if "." in path.stem:  # a copy of another session's theory
            continue
        for id_ in sorted(pages.ids(path)):
            m = ANCHOR_ID.fullmatch(id_)
            if m is not None:
                found.append(Anchor(m.group("name"), m.group("kind"), page))
    return found


def _suffixes(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[i:]) for i in range(len(parts))]


def _member(name: str) -> str:
    """``Theory.name`` for ``Theory.scope.name``; "" for a theory-level name."""
    parts = name.split(".")
    return f"{parts[0]}.{parts[-1]}" if len(parts) > 2 else ""


def _class_alias(name: str) -> str:
    """``T.c.x`` for ``T.c_class.x``: a class's facts and constants are
    rendered in its locale ``c`` and again in ``c_class``; "" otherwise."""
    parts = name.split(".")
    for i, part in enumerate(parts[:-1]):
        if part.endswith("_class"):
            return ".".join([*parts[:i], part.removesuffix("_class"), *parts[i + 1 :]])
    return ""


def _rank(anchor: Anchor, prefer: Sequence[str]) -> int:
    return next((i for i, p in enumerate(prefer) if anchor.page.startswith(p)), len(prefer))


class Index:
    """Anchors by the spellings that name them."""

    def __init__(self, anchors: Iterable[Anchor]) -> None:
        self._suffix: dict[str, list[Anchor]] = {}
        self._member: dict[str, list[Anchor]] = {}
        for anchor in anchors:
            for spelling in _suffixes(anchor.name):
                self._suffix.setdefault(spelling, []).append(anchor)
            if _member(anchor.name):
                self._member.setdefault(_member(anchor.name), []).append(anchor)

    def lookup(
        self, name: str, kinds: Sequence[str] = (), prefer: Sequence[str] = ()
    ) -> list[Anchor]:
        """The anchors ``name`` may mean: one if it resolves, none, or the
        rivals. A suffix of the id beats ``Theory.name`` for a member.
        ``kinds`` are tried in order, the first with a match wins; without
        them, the anchors of one definition count as one."""
        for hits in (self._suffix.get(name, []), self._member.get(name, [])):
            found = _of_kinds(hits, kinds)
            if found:
                return _preferred(found, prefer)
        return []


def _of_kinds(hits: list[Anchor], kinds: Sequence[str]) -> list[Anchor]:
    for kind in kinds:
        of_kind = [a for a in hits if a.kind == kind]
        if of_kind:
            return of_kind
    if kinds:
        return []
    order = {k: i for i, k in enumerate(KIND_ORDER)}
    one: dict[tuple[str, str], Anchor] = {}
    for anchor in sorted(hits, key=lambda a: (order.get(a.kind, len(order)), a.kind)):
        one.setdefault((anchor.page, anchor.name), anchor)
    return list(one.values())


def _preferred(anchors: list[Anchor], prefer: Sequence[str]) -> list[Anchor]:
    named = {(a.page, a.name) for a in anchors}
    anchors = [a for a in anchors if (a.page, _class_alias(a.name)) not in named]
    best = min(_rank(a, prefer) for a in anchors)
    return sorted(
        {a for a in anchors if _rank(a, prefer) == best}, key=lambda a: (a.page, a.name, a.kind)
    )
