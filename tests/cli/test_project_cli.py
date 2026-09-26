import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import Golden, MakeProject

PROJECT = {
    "ROOTS": "core\napp\n",
    "core/ROOT": 'chapter Demo\nsession Core = HOL + sessions "HOL-Library" theories A',
    "core/A.thy": "theory A imports Main B begin end",
    "core/B.thy": 'theory B imports "HOL-Library.Multiset" begin end',
    "app/ROOT": 'session "App-Main" = Core + theories C\nsession Again = Core + theories C\n'
    "session Bare = theories C",
    "app/C.thy": 'theory C imports "Core.A" begin end',
}


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PROJECT)
    monkeypatch.chdir(base)
    return base


@pytest.mark.parametrize(
    ("args", "name"),
    [
        (["project", "sessions"], "sessions.txt"),
        (["project", "theories", ".", "--format", "csv"], "theories.csv"),
        (["project", "graph"], "graph.txt"),
        (["project", "graph", "--format", "dot"], "graph.dot"),
        (["project", "graph", "--theories", "--format", "dot"], "theories.dot"),
        (["project", "graph", "--theories"], "theories_graph.txt"),
    ],
)
def test_views(
    project: Path, capsys: pytest.CaptureFixture[str], golden: Golden, args: list[str], name: str
) -> None:
    assert main(args) == 0
    golden(f"project/{name}", capsys.readouterr().out)


def test_graph_json(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "graph", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "nodes": ["Core", "App-Main", "Again", "Bare"],
        "edges": [
            {"from": "Core", "to": "HOL", "kind": "parent"},
            {"from": "Core", "to": "HOL-Library", "kind": "sessions"},
            {"from": "App-Main", "to": "Core", "kind": "parent"},
            {"from": "Again", "to": "Core", "kind": "parent"},
        ],
    }


def test_not_a_directory(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "sessions", "core/A.thy"]) == 2
    assert capsys.readouterr().err == "isar project: core/A.thy: not a directory\n"
