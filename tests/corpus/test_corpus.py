"""Integration tests over real Isabelle projects.

Opt-in: set ``ISAR_CORPUS`` to project directories separated by the platform
path separator, e.g. ``ISAR_CORPUS=$AFP/thys:$HOME/voblint``. Each directory
is loaded like ``isabelle build -D``. Nothing is vendored.
"""

import os
from pathlib import Path

import pytest

from isar_tools.formatter.formatter import format_theory
from isar_tools.project.model import Project
from isar_tools.source.lexer import LAYOUT, Kind, tokenize
from isar_tools.source.theory import parse_theory

CORPUS = [Path(p) for p in os.environ.get("ISAR_CORPUS", "").split(os.pathsep) if p]

pytestmark = pytest.mark.skipif(not CORPUS, reason="ISAR_CORPUS not set")


@pytest.fixture(scope="module", params=CORPUS, ids=str)
def project(request: pytest.FixtureRequest) -> Project:
    directory: Path = request.param
    return Project.load(directory)


def test_every_source_file_round_trips(project: Project) -> None:
    files = [r.path for r in project.roots if r.path is not None] + project.theory_files()
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "".join(t.text for t in tokenize(text)) == text, path


def test_roots_parse_without_diagnostics(project: Project) -> None:
    assert project.problems == []


def test_reached_theories_lex_without_errors(project: Project) -> None:
    broken = [
        path
        for path in project.theory_files()
        if any(t.kind is Kind.ERROR for t in tokenize(path.read_text(encoding="utf-8")))
    ]
    assert broken == []


def test_every_goal_block_closes(project: Project) -> None:
    unclosed: list[str] = []
    for path in project.theory_files():
        theory = parse_theory(path.read_text(encoding="utf-8"), project.keywords_for(path))
        for block in theory.goal_blocks():
            if not block.closed:
                line = theory.lines.line(theory.start(theory.commands[block.statement]))
                unclosed.append(f"{path}:{line}")
    assert unclosed == []


def test_formatter_changes_only_layout_and_is_idempotent(project: Project) -> None:
    for path in project.theory_files():
        text = path.read_bytes().decode("utf-8")
        keywords = project.keywords_for(path)
        once = format_theory(parse_theory(text, keywords))
        before = [(t.kind, t.text) for t in tokenize(text) if t.kind not in LAYOUT]
        after = [(t.kind, t.text) for t in tokenize(once) if t.kind not in LAYOUT]
        assert after == before, path
        assert format_theory(parse_theory(once, keywords)) == once, path
