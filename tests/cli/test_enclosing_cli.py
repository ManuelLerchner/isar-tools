import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import MakeProject

PROJECT = {
    "ROOT": "session S = HOL + theories A",
    "A.thy": """\
theory A imports Main begin
lemma two: "(2::nat) > 0"
proof -
  have "(1::nat) > 0" by simp
  then show ?thesis by simp
qed
end
""",
    "notes.txt": "",
}


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PROJECT)
    monkeypatch.chdir(base)
    return base


def test_enclosing(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "enclosing", "A.thy:4", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)["enclosing"]
    assert [(r["depth"], r["command"], r["text"], r["line"], r["end_line"]) for r in rows] == [
        (1, "lemma", "A.two", 2, 6),
        (2, "have", '"(1::nat) > 0"', 4, 4),
    ]
    assert main(["project", "enclosing", "A.thy:5"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "Enclosing A.thy:5"


def test_no_declaration(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "enclosing", "A.thy:1"]) == 1
    assert "A.thy:1: no declaration" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("location", "error"),
    [
        ("A.thy", "A.thy: expected FILE:LINE"),
        (":3", ":3: expected FILE:LINE"),
        ("A.thy:0", "A.thy:0: expected FILE:LINE"),
        ("notes.txt:1", "notes.txt: not a .thy file"),
        ("B.thy:1", "B.thy: not a .thy file"),
    ],
)
def test_bad_location(
    project: Path, capsys: pytest.CaptureFixture[str], location: str, error: str
) -> None:
    assert main(["project", "enclosing", location]) == 2
    assert error in capsys.readouterr().err
