import io
import sys
from pathlib import Path

import pytest

from isar_tools.cli import main
from isar_tools.source.files import read_source, write_source
from tests.conftest import MakeProject

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


def test_colored_diff(thy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fmt", "--diff", "--color", "always", "T.thy"]) == 1
    assert "\x1b[32m+  by simp\x1b[0m" in capsys.readouterr().out


def test_missing_include_directory_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mistyped `-d` would silently drop the commands it should provide."""
    with pytest.raises(SystemExit) as exit_info:
        main(["fmt", "--check", "-d", str(tmp_path / "missing"), str(tmp_path)])
    assert exit_info.value.code == 2
    assert "missing: not a directory" in capsys.readouterr().err


def test_configuration_file(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    long = "lemma x: " + " \\<and> ".join(["True"] * 30)
    base = make_project(
        {
            "isar.toml": 'exclude = ["gen/**"]\n[fmt]\nmax-line-length = 40\nindent = 4\n',
            "ROOT": "session S = HOL + theories A",
            "A.thy": f"theory A imports Main begin\n{long}\n  by simp\nend\n",
            "gen/G.thy": "theory G imports Main begin\nlemma y: True\nby simp\nend\n",
        }
    )
    monkeypatch.chdir(base)
    # The file sets wrapping and the indent step, and leaves gen/ out.
    assert main(["fmt", "--check", "."]) == 1
    assert capsys.readouterr().out.splitlines() == ["A.thy"]
    assert main(["fmt", "--diff", "A.thy"]) == 1
    assert "\n+        True" in capsys.readouterr().out  # continuation: two steps of 4
    # The command line wins: 0 turns wrapping off, --indent 2 overrides 4.
    assert main(["fmt", "--check", "--max-line-length", "0", "--indent", "2", "."]) == 0
    # --exclude adds to the file's list; a named file that matches is left out too.
    assert main(["fmt", "--check", "--exclude", "A.thy", "."]) == 0
    assert main(["fmt", "--check", "gen/G.thy"]) == 0
    assert capsys.readouterr().out == ""


def test_invalid_configuration_file(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(make_project({"isar.toml": "[fmt]\nwidth = 1\n"}))
    assert main(["fmt", "--check", "."]) == 2
    assert "[fmt] has no option 'width'" in capsys.readouterr().err
