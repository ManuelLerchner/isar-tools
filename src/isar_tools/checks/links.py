"""``links`` group: links from HTML and Markdown into Isabelle's HTML theories.

Isabelle's HTML presentation (``browser_info``) gives each definition an
anchor, ``<span class="entity_def" id="Theory.loc.name|kind">``, on the page
``Chapter/Session/Theory.html``. A link to one breaks silently: the page loads
and the anchor does nothing. The scope is the usual trap. A lemma inside
``context loc`` is ``Theory.loc.name``, and ``Theory.name`` names no anchor.

With ``--browser-info DIR`` (a built presentation), a link is checked when it
points into DIR: relative to the linking file, below a ``--link-base`` URL, or
relative and starting with a chapter directory of DIR, as on a site that
serves the presentation at its root. Then
the page must exist (``broken-link``) and hold the anchor (``broken-anchor``).

Without a build, links whose fragment is an anchor (``Theory.x|kind``, on a
page named ``Theory.html``) are compared with the project's declarations
(``anchor-name``): the anchor must start with its page's theory, and a name
declared exactly once in that theory must be spelt with its scope as the
theory declares it. A name declared twice, or one ``names --derived`` does not
list (a fact a locale inherits, say), is left alone.
"""

import html
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urldefrag

from isar_tools.checks.findings import Finding
from isar_tools.project.model import Project
from isar_tools.project.names import (
    Entity,
    Interpretation,
    anchor,
    entities,
    interpretations,
    interpreted,
)
from isar_tools.source.files import read_source
from isar_tools.source.lexer import LineIndex
from isar_tools.source.theory import parse_theory

LINK_SUFFIXES = frozenset({".html", ".htm", ".md", ".markdown"})
# href="..." in HTML; [text](target) and <scheme://...> in Markdown.
_LINK = re.compile(
    r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')|\]\(\s*<?([^)\s>]+)|<(\w+://[^>\s]+)>"""
)
ANCHOR_ID = re.compile(r"(?P<name>[^|]+)\|(?P<kind>[a-z_]+)")


@dataclass(frozen=True)
class Link:
    target: str
    offset: int


def links(text: str) -> Iterator[Link]:
    """The link targets of an HTML or Markdown text, with their offsets."""
    for m in _LINK.finditer(text):
        index = next(i for i in range(1, 5) if m.group(i) is not None)
        yield Link(html.unescape(m.group(index)), m.start(index))


class Pages:
    """Anchor ids of built pages, read once each."""

    def __init__(self) -> None:
        self._ids: dict[Path, set[str]] = {}

    def ids(self, page: Path) -> set[str]:
        if page not in self._ids:
            found = re.findall(r'\bid="([^"]*)"', read_source(page))
            self._ids[page] = {html.unescape(i) for i in found}
        return self._ids[page]


def _in_build(
    link: str, source: Path, browser_info: Path, bases: Iterable[str]
) -> tuple[Path, str] | None:
    """The page below ``browser_info`` that ``link`` points to, and its
    fragment; None for a link elsewhere."""
    url, fragment = urldefrag(link)
    root = browser_info.resolve()
    base = next((b for b in bases if url.startswith(b)), None)
    if base is not None:
        page = root / unquote(url.removeprefix(base))
    elif url and ":" not in url and not url.startswith("/"):
        page = (source.parent / unquote(url)).resolve()
        # A site that serves the presentation at its root links `Chapter/...`.
        first = unquote(url).split("/")[0]
        if (
            not page.is_relative_to(root)
            and first not in ("", ".", "..")
            and (root / first).is_dir()
        ):
            page = root / unquote(url)
    else:
        return None
    page = page.resolve()
    return (page, unquote(fragment)) if page.is_relative_to(root) and page != root else None


def check_built(
    path: Path, text: str, browser_info: Path, bases: Iterable[str], pages: Pages
) -> list[Finding]:
    lines = LineIndex(text)
    findings: list[Finding] = []
    for link in links(text):
        found = _in_build(link.target, path, browser_info, bases)
        if found is None:
            continue
        page, fragment = found
        if not page.is_file():
            missing = page.relative_to(browser_info.resolve()).as_posix()
            message = f"{link.target}: no page {missing}"
            findings.append(Finding.at(path, lines, link.offset, "broken-link", message))
        elif fragment and fragment not in pages.ids(page):
            message = f"{link.target}: {page.name} has no anchor {fragment}"
            findings.append(Finding.at(path, lines, link.offset, "broken-anchor", message))
    return findings


def declared_anchors(project: Project) -> dict[tuple[str, str], list[str]]:
    """``(theory, base name)`` to the anchor names declaring it, as
    ``names --derived`` lists them, of the project and its ``-d`` directories."""
    found: list[Entity] = []
    interps: list[Interpretation] = []
    for session in project.sessions.values():
        for name, path in project.owned_theories(session).items():
            theory = parse_theory(read_source(path), project.keywords_for(path))
            found += entities(theory, name, path, derived=True)
            interps += interpretations(theory, name, path)
    found += [e for i in interps for e in interpreted(found, i)]
    declared: dict[tuple[str, str], list[str]] = {}
    for entity in found:
        name = anchor(entity).partition("|")[0]
        key = (entity.theory, name.rpartition(".")[2])
        if name and name not in declared.get(key, []):
            declared.setdefault(key, []).append(name)
    return declared


def check_sources(
    path: Path, text: str, declared: dict[tuple[str, str], list[str]]
) -> list[Finding]:
    lines = LineIndex(text)
    findings: list[Finding] = []
    for link in links(text):
        url, fragment = urldefrag(link.target)
        m = ANCHOR_ID.fullmatch(unquote(fragment))
        if m is None or not url.endswith(".html"):
            continue
        # A session-qualified page (`S.Theory.html`) holds the theory's own ids.
        theory = unquote(url).rpartition("/")[2].removesuffix(".html").rpartition(".")[2]
        name = m.group("name")
        if not name.startswith(f"{theory}."):
            message = f"{link.target}: the anchor does not start with {theory}."
        else:
            hits = declared.get((theory, name.rpartition(".")[2]), [])
            if len(hits) != 1 or hits[0] == name:
                continue
            message = f"{link.target}: {theory} declares it as {hits[0]}"
        findings.append(Finding.at(path, lines, link.offset, "anchor-name", message))
    return findings


def check_links(
    files: Iterable[Path],
    projects: Iterable[Project],
    browser_info: Path | None,
    bases: Iterable[str] = (),
) -> list[Finding]:
    """Findings for the links of ``files``: against the build in
    ``browser_info``, or, without one, against the declarations of
    ``projects``."""
    pages = Pages()
    declared: dict[tuple[str, str], list[str]] | None = None
    findings: list[Finding] = []
    for path in files:
        text = read_source(path)
        if browser_info is not None:
            findings += check_built(path, text, browser_info, list(bases), pages)
            continue
        if declared is None:
            declared = {}
            for project in projects:
                for key, names in declared_anchors(project).items():
                    declared.setdefault(key, []).extend(names)
        findings += check_sources(path, text, declared)
    return findings
