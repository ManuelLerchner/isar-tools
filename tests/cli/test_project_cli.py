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
        (["project", "graph", "--layers"], "layers.txt"),
        (["project", "graph", "--layers", "--format", "dot"], "layers.dot"),
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


def test_layers_json(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "app/D.thy").write_text('theory D imports "Core.B" "App-Main.C" begin end')
    (project / "app/ROOT").write_text(
        'session "App-Main" = Core + theories C\nsession Again = HOL + theories D\n'
        "session Bare = theories C"
    )
    assert main(["project", "graph", "--layers", "--format", "json"]) == 0
    graph = json.loads(capsys.readouterr().out)
    assert graph["layers"] == {"Core": 1, "App-Main": 2, "Bare": 2, "Again": 3}
    assert {"from": "Again", "to": "Core", "kind": "imports"} in graph["edges"]
    assert {"from": "Again", "to": "Bare", "kind": "imports"}  # Bare owns C in graph["edges"]


def test_layers_of_theories(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "graph", "--layers", "--theories"]) == 2
    assert "--layers is a view of sessions" in capsys.readouterr().err
    (project / "empty").mkdir()
    assert main(["project", "graph", "--layers", "empty"]) == 0
    assert capsys.readouterr().out == ""
