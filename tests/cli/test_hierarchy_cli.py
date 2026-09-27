import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import Golden, MakeProject

PROJECT = {
    "own/ROOT": "session Own = Base + theories Domain",
    "own/Domain.thy": """\
theory Domain imports Main begin
class numeric = lattice +
  fixes gamma :: "'a::order_top \\<Rightarrow> int set" ("\\<gamma>")
  assumes gamma_mono: "a \\<le> b \\<Longrightarrow> \\<gamma> a \\<subseteq> \\<gamma> b"
locale evaluator =
  fixes eval :: "'d \\<Rightarrow> 'a::numeric"
  assumes sound: "P"
locale mono_evaluator = evaluator +
  assumes mono: "Q"
end
""",
    "lib/ROOT": 'session Base = Pure + theories Main "Lattices"',
    "lib/Main.thy": "theory Main imports Lattices begin end",
    "lib/Lattices.thy": """\
theory Lattices imports Pure begin
class lattice = order +
  fixes inf :: "'a \\<Rightarrow> 'a \\<Rightarrow> 'a" (infixl "\\<sqinter>" 70)
end
""",
    "lib/Unrelated.thy": "theory Unrelated imports Pure begin\nclass numeric\nend",
}


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PROJECT)
    monkeypatch.chdir(base)
    return base


HIERARCHY = ["project", "hierarchy", "own"]


@pytest.mark.parametrize(
    ("args", "name"),
    [
        ([], "all.txt"),
        (["-d", "lib"], "own_only.txt"),
        (["--root", "mono_evaluator", "-d", "lib"], "root.txt"),
        (["--root", "mono_evaluator", "--format", "dot"], "root.dot"),
        (["--root", "evaluator", "--root", "numeric", "-d", "lib", "--format", "dot"], "sorts.dot"),
        (["--root", "numeric", "-d", "lib", "--format", "json"], "numeric.json"),
    ],
)
def test_views(
    project: Path, capsys: pytest.CaptureFixture[str], golden: Golden, args: list[str], name: str
) -> None:
    assert main([*HIERARCHY, *args]) == 0
    golden(f"hierarchy/{name}", capsys.readouterr().out)


def test_parents_resolve_through_imports_only(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["project", "hierarchy", "own", "--root", "numeric", "-d", "lib", "--format", "json"])
        == 0
    )
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert [(d["name"], d["session"], d["external"]) for d in data["declarations"]] == [
        ("lattice", "Base", True),
        ("numeric", "Own", False),
    ]
    # `order` is not declared anywhere visible: reported, not guessed.
    assert data["unresolved"] == ["order", "order_top"]
    assert err == (
        "isar project hierarchy: warning: no class or locale order\n"
        "isar project hierarchy: warning: no class or locale order_top\n"
    )


def test_without_include_parents_are_unresolved(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["project", "hierarchy", "own", "--root", "mono_evaluator", "--format", "json"]) == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert [d["name"] for d in data["declarations"]] == ["evaluator", "mono_evaluator"]
    assert data["unresolved"] == []
