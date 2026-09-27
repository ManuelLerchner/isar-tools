import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import Golden, MakeProject

PROJECT = {
    "ROOT": "session S = HOL + directories gone theories A B",
    "A.thy": 'theory A imports Main begin\nlemma x: "A ⟹ A" sorry\ntext\nend\n',
    "B.thy": 'theory B imports "Lib.L" begin\ntext \\<open>ok\\<close>\nlibcmd foo\nend\n',
    "lib/ROOT": "session Lib = HOL + theories L",
    "lib/L.thy": 'theory L imports Main keywords "libcmd" :: thy_decl begin end',
}


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PROJECT)
    monkeypatch.chdir(base)
    return base


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    status = main(["check", *args])
    out, err = capsys.readouterr()
    return status, out, err


def test_default_groups(project: Path, capsys: pytest.CaptureFixture[str], golden: Golden) -> None:
    status, out, err = run(capsys, "A.thy", "B.thy")
    assert status == 1
    assert err == "3 finding(s)\n"
    golden("check/default.txt", out)


def test_group_and_ignore(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "symbols", "A.thy")
    assert status == 1
    assert out.startswith("A.thy:2:13: non-ascii: non-ASCII character '⟹'")
    status, out, err = run(capsys, "symbols", "A.thy", "--ignore", "non-ascii")
    assert (status, out, err) == (0, "", "")


def test_project_group_and_include(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "--group", "project", ".")
    assert status == 1
    assert out.splitlines() == [
        "ROOT:1:31: missing-directory: directories entry 'gone' of S does not exist",
    ]
    status, out, _ = run(capsys, "--group", "syntax", "B.thy")
    assert status == 1
    assert "unexpected 'libcmd' after the text of text" in out
    status, out, _ = run(capsys, "--group", "syntax", "B.thy", "-d", "lib")
    assert (status, out) == (0, "")


def test_json(project: Path, capsys: pytest.CaptureFixture[str], golden: Golden) -> None:
    status, out, _ = run(capsys, "A.thy", "--format", "json")
    assert status == 1
    assert [f["code"] for f in json.loads(out)["findings"]] == [
        "unfinished-proof",
        "document-argument",
    ]
    golden("check/a.json", out)


def test_clean(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "lib", "--format", "csv") == (
        0,
        "path,line,column,code,message\n",
        "",
    )


def test_help_lists_codes(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["check", "--help"])
    assert "unreached-theory" in capsys.readouterr().out
