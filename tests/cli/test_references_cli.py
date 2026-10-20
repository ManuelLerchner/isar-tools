import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import MakeProject

PROJECT = {
    "ROOT": "session S = HOL + theories A B",
    "A.thy": """\
theory A imports Main begin
definition succ :: "nat \\<Rightarrow> nat" where "succ n = n + 1"
lemma succ_pos: "succ n > 0" unfolding succ_def by simp
end
""",
    "B.thy": """\
theory B imports A begin
lemma succ_ge: "succ n \\<ge> 1" using succ_pos by (simp add: Suc_le_eq)
lemma succ_pos: "True" by simp
end
""",
}


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PROJECT)
    monkeypatch.chdir(base)
    return base


def rows(capsys: pytest.CaptureFixture[str]) -> list[tuple[str, int]]:
    return [(r["name"], r["depth"]) for r in json.loads(capsys.readouterr().out)["callers"]]


def test_callers(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "callers", "succ", "--format", "json"]) == 0
    assert rows(capsys) == [("A.succ_pos", 1), ("B.succ_ge", 1)]
    assert main(["project", "callers", "succ", "-r", "--format", "json"]) == 0
    assert rows(capsys) == [("A.succ_pos", 1), ("B.succ_ge", 1)]


def test_callees(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "callees", "B.succ_ge", "-r"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "Callees of B.succ_ge"
    assert [line.split()[0] for line in out.splitlines()[3:]] == ["A.succ", "A.succ_pos"]


def test_unknown(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "callers", "nope"]) == 1
    assert "isar project callers: nope: no declaration" in capsys.readouterr().err
    assert main(["project", "callees", "succ_pos"]) == 1
    assert "succ_pos: ambiguous" in capsys.readouterr().err
