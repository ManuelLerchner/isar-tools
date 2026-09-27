import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import Golden, MakeProject

PROJECT = {
    "ROOT": "session S = HOL + theories A B",
    "A.thy": """\
theory A imports Main begin
definition succ :: "nat \\<Rightarrow> nat" where
  "succ n = n + 1"

lemma succ_pos: "succ n > 0"
  unfolding succ_def by simp
end
""",
    "B.thy": """\
theory B imports A begin
locale l = fixes x :: nat begin
lemma succ_pos: "succ x > 0"
  by (rule A.succ_pos)
end
end
""",
    "snippets.toml": """\
[snippets.succ]
why = "shown in chapter 2"

[snippets."l.succ_pos"]
""",
}


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PROJECT)
    monkeypatch.chdir(base)
    return base


EXTRACT = ["project", "extract"]


def test_print(project: Path, capsys: pytest.CaptureFixture[str], golden: Golden) -> None:
    assert main([*EXTRACT, "succ", "A.succ_pos"]) == 0
    golden("extract/print.txt", capsys.readouterr().out)


def test_json(project: Path, capsys: pytest.CaptureFixture[str], golden: Golden) -> None:
    assert main([*EXTRACT, "B.l.succ_pos", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)[0]["qualified"] == "B.l.succ_pos"
    golden("extract/one.json", out)


def test_missing_and_ambiguous(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*EXTRACT, "succ_pos", "nope", "succ"]) == 1
    captured = capsys.readouterr()
    assert captured.err.splitlines() == [
        "isar project extract: succ_pos: ambiguous: A.succ_pos (A.thy:5), B.l.succ_pos (B.thy:3)",
        "isar project extract: nope: no declaration",
    ]
    assert captured.out.startswith("(* A.thy *)\ndefinition succ")


def test_manifest_write_then_check(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = [*EXTRACT, "--manifest", "snippets.toml", "--out", "out"]
    assert main([*manifest, "--check"]) == 1
    assert "2 snippet(s) differ" in capsys.readouterr().err
    assert main([*manifest, "--write"]) == 0
    assert capsys.readouterr().out == "wrote out/l.succ_pos.thy\nwrote out/succ.thy\n"
    assert (project / "out/succ.thy").read_text().startswith("(* A.thy *)\ndefinition succ ::")
    assert main([*manifest, "--check"]) == 0
    assert main([*manifest, "--write"]) == 0
    assert capsys.readouterr().out == ""
    # An edit to a shown declaration is drift.
    text = (project / "A.thy").read_text().replace("n + 1", "Suc n")
    (project / "A.thy").write_text(text)
    assert main([*manifest, "--check", "--color", "never"]) == 1
    out = capsys.readouterr().out
    assert '-  "succ n = n + 1"\n+  "succ n = Suc n"\n' in out


def test_manifest_file_pins(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "pin.toml").write_text('[snippets.succ_pos]\nfile = "B.thy"\n')
    assert main([*EXTRACT, "--manifest", "pin.toml", "--out", "o", "--write"]) == 0
    assert (project / "o/succ_pos.thy").read_text().startswith("(* B.thy *)\n")
    (project / "pin.toml").write_text('[snippets.succ]\nfile = "B.thy"\n[snippets.nope]\n')
    assert main([*EXTRACT, "--manifest", "pin.toml", "--out", "o", "--write"]) == 1
    assert capsys.readouterr().err.splitlines() == [
        "isar project extract: nope: no declaration",
        "isar project extract: succ: no declaration in B.thy",
    ]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "give a NAME or --manifest"),
        (["x", "--write"], "--out, --write, and --check need --manifest"),
        (["--manifest", "snippets.toml", "--write"], "--manifest takes no NAME and needs --out"),
        (["x", "--manifest", "snippets.toml", "--out", "o"], "--manifest takes no NAME"),
        (["--manifest", "snippets.toml", "--out", "o"], "--manifest needs --write or --check"),
        (["--manifest", "absent.toml", "--out", "o", "--check"], "absent.toml"),
        (["--manifest", "bad.toml", "--out", "o", "--check"], "bad.toml"),
        (["--manifest", "list.toml", "--out", "o", "--check"], "[snippets] must be a table"),
        (["x", "--project", "nowhere"], "nowhere: not a directory"),
    ],
)
def test_invalid(
    project: Path, capsys: pytest.CaptureFixture[str], args: list[str], message: str
) -> None:
    (project / "bad.toml").write_text("[snippets\n")
    (project / "list.toml").write_text("snippets = [1]\n")
    assert main([*EXTRACT, *args]) == 2
    assert message in capsys.readouterr().err
