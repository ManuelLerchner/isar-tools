"""Snapshots of ``isar check --fix``: each project under ``tests/fix`` is
fixed in a copy, and the report and every file are compared with
``tests/golden/fix/<case>/<mode>/``. ``UPDATE_GOLDEN=1`` rewrites them, so a
change in what a fix does shows up as a diff in review."""

import shutil
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import Golden, MakeProject

CASES = Path(__file__).parent.parent / "fix"


@pytest.mark.parametrize("mode", ["safe", "all"])
@pytest.mark.parametrize("case", sorted(p.name for p in CASES.iterdir() if p.is_dir()))
def test_fix_snapshots(
    case: str,
    mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    golden: Golden,
) -> None:
    project = tmp_path / case
    shutil.copytree(CASES / case, project)
    monkeypatch.chdir(project)
    status = main(["check", "--group", "all", f"--fix={mode}", "."])
    out, err = capsys.readouterr()
    golden(f"fix/{case}/{mode}/report.txt", f"exit {status}\n{out}--- stderr\n{err}")
    for path in sorted(project.rglob("*")):
        if path.is_file():
            rel = path.relative_to(project).as_posix()
            golden(f"fix/{case}/{mode}/{rel}", path.read_text(encoding="utf-8"))


def test_hygiene_fixes(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories H\n",
            "H.thy": "theory H imports Main begin\r\ntext \\<open>x\u202ey\\<close>\r\n"
            'lemma h: "True"\r\n\tby simp\r\nend\r\n',
        }
    )
    monkeypatch.chdir(base)
    assert main(["check", "hygiene", "--fix", "."]) == 0
    _, err = capsys.readouterr()
    assert err == "fixed 3 findings\nno findings\n"
    assert (base / "H.thy").read_bytes() == (
        b'theory H imports Main begin\ntext \\<open>xy\\<close>\nlemma h: "True"\n  by simp\nend\n'
    )


def test_fixable_note(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {"T.thy": 'theory T imports Main begin\nlemma t: "True" by (simp add:)\nend\n'}
    )
    monkeypatch.chdir(base)
    assert main(["check", "methods", "unused", "T.thy"]) == 1
    _, err = capsys.readouterr()
    assert err.splitlines()[-1] == "1 fixable with --fix, 1 more with --fix=all"
    assert main(["check", "unused", "T.thy"]) == 1
    _, err = capsys.readouterr()
    assert err.splitlines()[-1] == "1 with --fix=all"
