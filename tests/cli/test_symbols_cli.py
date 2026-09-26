from pathlib import Path

import pytest

from isar_tools.cli import main
from isar_tools.source.files import read_source, write_source

UNICODE = 'lemma "A ⟹ B" (* é *)\r\ntext ‹λx›\r\n'
ASCII = 'lemma "A \\<Longrightarrow> B" (* é *)\r\ntext \\<open>\\<lambda>x\\<close>\r\n'


@pytest.fixture
def thy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "T.thy"
    write_source(path, UNICODE)
    return path


def test_normalize_in_place_keeps_line_endings(
    thy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["symbols", "normalize", "."]) == 0
    assert read_source(thy) == ASCII
    assert capsys.readouterr().err == "normalized T.thy\n"
    assert main(["symbols", "normalize", "T.thy"]) == 0
    assert capsys.readouterr().err == ""


def test_to_unicode_round_trips(thy: Path) -> None:
    write_source(thy, ASCII)
    assert main(["symbols", "normalize", "--to", "unicode", "T.thy"]) == 0
    assert read_source(thy) == UNICODE


def test_check(thy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["symbols", "normalize", "--check", "T.thy"]) == 1
    assert capsys.readouterr().out == "T.thy\n"
    assert read_source(thy) == UNICODE
    write_source(thy, ASCII)
    assert main(["symbols", "normalize", "--check", "T.thy"]) == 0


def test_diff(thy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["symbols", "normalize", "--diff", "T.thy"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("--- a/T.thy\n+++ b/T.thy\n")
    assert "+text \\<open>\\<lambda>x\\<close>" in out
    assert read_source(thy) == UNICODE


def test_action_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["symbols"])
    assert exc.value.code == 2
