import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from isar_tools.stats.views import percentile
from tests.conftest import Golden, MakeProject

PROJECT = {
    "ROOTS": "Core\nApps\n",
    "Core/ROOT": "session Core = HOL + theories Basics Big",
    "Core/Basics.thy": """\
theory Basics imports Main begin

definition double :: "nat \\<Rightarrow> nat" where "double n = n + n"

lemma double_simp [simp]: "double n = 2 * n"
  by (simp add: double_def)

end
""",
    "Core/Big.thy": """\
theory Big imports Basics begin

text \\<open>A longer theory.\\<close>

lemma long_proof:
  assumes "x = (1::nat)"
  shows "double x = 2"
proof -
  have "double x = 2 * x"
    by simp
  also have "\\<dots> = 2"
    using assms by metis
  finally show ?thesis .
qed

lemma gap: "False"
  sorry

end
""",
    "Apps/ROOT": 'session "Core-Apps" in "." = Core + theories App',
    "Apps/App.thy": """\
theory App imports "Core.Big" begin

fun f :: "nat \\<Rightarrow> nat" where "f 0 = 0" | "f (Suc n) = f n"

lemma f_zero: "f n = 0" by (induct n) auto

end
""",
}


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PROJECT)
    monkeypatch.chdir(base)
    return base


@pytest.mark.parametrize(
    ("args", "name"),
    [
        (["stats"], "summary.txt"),
        (["stats", ".", "--format", "markdown"], "summary.md"),
        (["stats", "sessions", "."], "sessions.txt"),
        (["stats", "theories", ".", "--sort", "name", "--top", "2"], "theories_top2.txt"),
        (["stats", "proofs", ".", "--format", "csv"], "proofs.csv"),
        (["stats", "commands", "."], "commands.txt"),
        (
            ["stats", "style", ".", "--max-theory-lines", "15", "--max-line-length", "40"],
            "style.txt",
        ),
        (["stats", "theories", "Core", "--session", "Core", "--format", "json"], "core.json"),
        (["stats", "style", "."], "style_default.txt"),
    ],
)
def test_views(
    project: Path, capsys: pytest.CaptureFixture[str], golden: Golden, args: list[str], name: str
) -> None:
    assert main(args) == 0
    out, err = capsys.readouterr()
    assert err == ""
    golden(f"stats/{name}", out)


def test_json_is_machine_readable(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["stats", ".", "--format", "json", "--watch", "auto"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"sessions", "theories"}
    total = data["sessions"][-1]
    assert total["session"] == "TOTAL"
    assert total["theories"] == 3
    assert total["unfinished"] == 1


def test_no_theories(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["stats", ".", "--session", "Nope"]) == 2
    assert capsys.readouterr().err == "isar stats: no .thy files found\n"


def test_bad_path(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["stats", "missing"]) == 2
    assert capsys.readouterr().err == "isar stats: missing: no such file or directory\n"


def test_stats_help_is_not_rewritten(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["stats", "--help"])
    assert exc.value.code == 0
    assert "<view>" in capsys.readouterr().out


def test_single_session_has_no_total(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["stats", "sessions", "Core", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)["sessions"]
    assert [r["session"] for r in rows] == ["Core"]


def test_paths_outside_cwd_are_absolute(
    project: Path, tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (elsewhere / "X.thy").write_text("theory X imports Main begin end", encoding="utf-8")
    assert main(["stats", "theories", str(elsewhere), "--format", "json"]) == 0
    row = json.loads(capsys.readouterr().out)["theories"][0]
    assert row["path"] == (elsewhere / "X.thy").resolve().as_posix()
    assert row["session"] == "-"


@pytest.mark.parametrize(
    ("xs", "q", "expected"),
    [([], 90, 0), ([5], 90, 5), ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90, 9), ([3, 1, 2], 50, 2)],
)
def test_percentile(xs: list[int], q: float, expected: int) -> None:
    assert percentile(xs, q) == expected


def test_configuration_file(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = make_project(
        {
            "isar.toml": '[stats]\nmax-line-length = 10\nwatch = ["blast"]\n',
            "ROOT": "session S = HOL + theories A",
            "A.thy": "theory A imports Main begin\nlemma x: True by blast\nend\n",
        }
    )
    monkeypatch.chdir(base)
    assert main(["stats", "style", "--format", "json", "."]) == 0
    (row,) = json.loads(capsys.readouterr().out)["style"]
    assert row["long_lines"] == 2
    assert row["methods"] == "blast=1"
    # The command line wins over the file.
    assert main(["stats", "style", "--max-line-length", "100", "--format", "json", "."]) == 0
    (row,) = json.loads(capsys.readouterr().out)["style"]
    assert row["long_lines"] == 0


def test_commands_per_theory(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories A B",
            "A.thy": "theory A imports Main begin\n"
            "lemma x: True by simp\nlemma y: True by simp\nend\n",
            "B.thy": 'theory B imports A begin\ndefinition c :: nat where "c = 0"\nend\n',
        }
    )
    monkeypatch.chdir(base)
    assert main(["stats", "commands", "--by", "theory", "--format", "json", "."]) == 0
    rows = json.loads(capsys.readouterr().out)["commands"]
    assert {(r["theory"], r["command"]): r["count"] for r in rows} == {
        ("A", "lemma"): 2,
        ("A", "by"): 2,
        ("A", "theory"): 1,
        ("A", "end"): 1,
        ("B", "definition"): 1,
        ("B", "theory"): 1,
        ("B", "end"): 1,
    }
    assert rows[0] == {"session": "S", "theory": "A", "command": "by", "count": 2, "path": "A.thy"}
