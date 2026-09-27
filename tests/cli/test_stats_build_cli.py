# Synthetic build log. Every recognised line uses the one evidence-backed
# format, `BUILDER: theory OWNER.THEORY 100% (Ns cumulated time)`, observed in
# real Isabelle2025 `isabelle build -v` logs; the other lines are noise that must
# be ignored. Session and theory names are made up.

import json
from pathlib import Path
from typing import Any

import pytest

from isar_tools.cli import main
from isar_tools.stats.cli import normalize_argv
from tests.conftest import Golden

LOG = """\
Building Lib ...
Lib: theory Lib.Graph 100% (12.4s cumulated time)
Lib: theory HOL-Library.Monad_Syntax 100% (1.5s cumulated time)
Finished Lib (0:00:15 elapsed time)
Core: theory Core.Syntax 100% (30.0s cumulated time)
Core: theory HOL-Library.Monad_Syntax 100% (1.25s cumulated time)
Core: theory Lib.Graph 100% (11.0s cumulated time)
Analysis_A: theory Lib.Graph 100% (13s cumulated time)
Analysis_A: theory Analysis_A.Domain 100% (45.5s cumulated time)
Analysis_B: theory HOL-Library.Monad_Syntax 100% (1.75s cumulated time)
Analysis_B: theory Analysis_B.Domain 100% (40.0s cumulated time)
"""


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "build.log"
    path.write_text(LOG, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("args", "name"),
    [
        (["stats", "build", "build.log"], "build.txt"),
        (["stats", "build", "build.log", "--format", "json"], "build.json"),
        (
            ["stats", "build", "build.log", "--top", "1", "--budget", "Lib=2", "--budget", "X=0"],
            "build_budgets.txt",
        ),
    ],
)
def test_views(
    log: Path, capsys: pytest.CaptureFixture[str], golden: Golden, args: list[str], name: str
) -> None:
    assert main(args) == 0
    out, err = capsys.readouterr()
    assert err == ""
    golden(f"stats/{name}", out)


def test_json_keys(log: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["stats", "build", "build.log", "--format", "json", "--budget", "Lib=5"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"sessions", "reelaborated", "budgets"}
    assert set(data["reelaborated"][0]) == {"theory", "elaborations", "wasted_seconds", "sessions"}
    assert data["budgets"] == [
        {"session": "Lib", "elaborations": 2, "budget": 5, "cpu_seconds": 24.0, "ok": True}
    ]


def test_over_budget(log: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["stats", "build", "build.log", "--budget", "Lib=1", "--budget", "HOL-Library=0"]
    assert main(args) == 1
    out, err = capsys.readouterr()
    assert "Elaborations of a session's theories inside other sessions" in out
    assert err == (
        "isar stats build: over budget: HOL-Library: 3 elaborations of its theories "
        "inside other sessions, budget 0 (4.5s cpu)\n"
        "isar stats build: over budget: Lib: 2 elaborations of its theories "
        "inside other sessions, budget 1 (24.0s cpu)\n"
    )


def test_duplicate_budget(log: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["stats", "build", "build.log", "--budget", "A=1", "--budget", "A=2"]) == 2
    assert capsys.readouterr().err == "isar stats: --budget A given twice\n"


@pytest.mark.parametrize("spec", ["A", "=1", "A=", "A=-1", "A=x"])
def test_bad_budget(log: Path, capsys: pytest.CaptureFixture[str], spec: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["stats", "build", "build.log", "--budget", spec])
    assert exc.value.code == 2
    assert "expected SESSION=N" in capsys.readouterr().err


def test_missing_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["stats", "build", "missing.log"]) == 2
    assert capsys.readouterr().err == "isar stats: missing.log: no such file\n"


def test_directory_is_not_a_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["stats", "build", "."]) == 2
    assert capsys.readouterr().err == "isar stats: .: no such file\n"


def test_unreadable_log(
    log: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Tests run as root in some environments, where chmod cannot deny reading.
    real_open = Path.open

    def refuse(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == "build.log":
            raise PermissionError(13, "Permission denied")
        return real_open(self, *args, **kwargs)  # pyright: ignore[reportUnknownVariableType]

    monkeypatch.setattr(Path, "open", refuse)
    assert main(["stats", "build", "build.log"]) == 2
    assert capsys.readouterr().err == "isar stats: build.log: Permission denied\n"


@pytest.mark.parametrize(
    ("text", "lines"),
    [("", 0), ("Building Lib ...\nFinished Lib (0:00:01 elapsed time)\n", 2)],
)
def test_no_elaboration_lines(
    log: Path, capsys: pytest.CaptureFixture[str], text: str, lines: int
) -> None:
    log.write_text(text, encoding="utf-8")
    assert main(["stats", "build", "build.log"]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("isar stats: build.log: no theory elaboration lines (")
    assert f"in {lines} lines. Either nothing was rebuilt, or this is not" in err


def test_concatenated_builds(log: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log.write_text(LOG + LOG, encoding="utf-8")
    assert main(["stats", "build", "build.log"]) == 2
    assert capsys.readouterr().err == (
        "isar stats: build.log: line 13: session Lib elaborates Lib.Graph again "
        "(first at line 2); is this several builds in one log?\n"
    )


def test_invalid_utf8_is_tolerated(log: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log.write_bytes(b"\xff\xfe noise\n" + LOG.encode())
    assert main(["stats", "build", "build.log", "--format", "csv"]) == 0
    assert capsys.readouterr().out.startswith("# sessions\n")


def test_build_is_a_view() -> None:
    assert normalize_argv(["stats", "build", "x.log"]) == ["stats", "build", "x.log"]
    assert normalize_argv(["stats", "src"]) == ["stats", "summary", "src"]
