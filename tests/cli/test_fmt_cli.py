import io
import sys
from pathlib import Path

import pytest

from isar_tools.cli import main
from isar_tools.source.files import read_source, write_source

UGLY = 'theory T imports Main begin\nlemma x: "A"\nby simp  \nend\n'
PRETTY = 'theory T imports Main begin\nlemma x: "A"\n  by simp\nend\n'


@pytest.fixture
def thy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    write_source(tmp_path / "T.thy", UGLY)
    write_source(tmp_path / "Ok.thy", PRETTY.replace("T", "Ok"))
    return tmp_path / "T.thy"


def test_in_place(thy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fmt"]) == 0
    assert read_source(thy) == PRETTY
    assert capsys.readouterr().err == "formatted T.thy\n"
    assert main(["fmt", "."]) == 0
    assert capsys.readouterr().err == ""


def test_check(thy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fmt", "--check", "."]) == 1
    assert capsys.readouterr().out == "T.thy\n"
    assert read_source(thy) == UGLY
    assert main(["fmt", "--check", "Ok.thy"]) == 0


def test_diff(thy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fmt", "--diff", "T.thy"]) == 1
    assert capsys.readouterr().out == (
        "--- a/T.thy\n+++ b/T.thy\n@@ -1,4 +1,4 @@\n"
        ' theory T imports Main begin\n lemma x: "A"\n-by simp  \n+  by simp\n end\n'
    )


def test_options(thy: Path) -> None:
    write_source(thy, 'lemma x: "A"\n   by simp\n')
    assert main(["fmt", "--normalize", "--indent", "4", "T.thy"]) == 0
    assert read_source(thy) == 'lemma x: "A"\n    by simp\n'
    write_source(thy, "end\n\n\n\nend\n")
    assert main(["fmt", "--max-blank-lines", "0", "T.thy"]) == 0
    assert read_source(thy) == "end\nend\n"


def test_max_line_length(thy: Path) -> None:
    write_source(thy, 'lemma x: "A"\n  using some_fact by simp\n')
    assert main(["fmt", "--max-line-length", "20", "T.thy"]) == 0
    assert read_source(thy) == 'lemma x: "A"\n  using some_fact\n  by simp\n'


def test_unformattable_file(thy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_source(thy, 'lemma "open\n')
    assert main(["fmt", "."]) == 2
    assert capsys.readouterr().err == (
        "isar fmt: T.thy: line 1: unterminated comment, string, or cartouche; not formatted\n"
    )
    assert read_source(thy) == 'lemma "open\n'


def test_check_with_unformattable_file(thy: Path) -> None:
    write_source(thy, 'lemma "open\n')
    assert main(["fmt", "--check", "."]) == 2


@pytest.mark.parametrize(("given", "status", "out"), [(UGLY, 0, PRETTY), ('"open', 2, "")])
def test_stdin(
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
    given: str,
    status: int,
    out: str,
) -> None:
    stdin = io.TextIOWrapper(io.BytesIO(given.encode()))
    monkeypatch.setattr(sys, "stdin", stdin)
    assert main(["fmt", "-"]) == status
    assert capsysbinary.readouterr().out == out.encode()
