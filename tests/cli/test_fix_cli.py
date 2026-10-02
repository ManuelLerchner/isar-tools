"""Snapshots of ``isar check --fix``: each project under ``tests/fix`` is
fixed in a copy, and the report and every file are compared with
``tests/golden/fix/<case>/<mode>/``. ``UPDATE_GOLDEN=1`` rewrites them, so a
change in what a fix does shows up as a diff in review."""

import shutil
from pathlib import Path

import pytest

from isar_tools.checks import cli as check_cli
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
    base = make_project({"ROOT": "session S = HOL + theories H\n"})
    # Bytes, so no platform translates the line endings under test.
    (base / "H.thy").write_bytes(
        b"theory H imports Main begin\r\ntext \\<open>x\xe2\x80\xaey\\<close>\r\n"
        b'lemma h: "True"\r\n\tby simp\r\nend\r\n'
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
        {
            "ROOT": "session S = HOL + theories A T\n",
            "A.thy": 'theory A imports Main begin\ndefinition a :: nat where "a = 0"\nend\n',
            "T.thy": 'theory T imports Main A begin\nlemma t [simp]: "True" by (simp add:)\nend\n',
        }
    )
    monkeypatch.chdir(base)
    assert main(["check", "methods", "unused", "T.thy"]) == 1
    _, err = capsys.readouterr()
    assert err.splitlines()[-1] == "1 fixable with --fix, 1 more with --fix=all"
    assert main(["check", "unused", "T.thy"]) == 1
    _, err = capsys.readouterr()
    assert err.splitlines()[-1] == "1 with --fix=all"


def test_all_takes_retired_when_it_has_names(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": "theory T imports Main begin\ntext \\<open>t\\<close>\n"
            'lemma "old_name = x" sorry\nend\n',
        }
    )
    monkeypatch.chdir(base)
    assert main(["check", "all", "--retired", "old_name", "."]) == 1
    out, _ = capsys.readouterr()
    assert "retired-identifier" in out


def test_rounds_are_bounded(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"ROOT": "session S = HOL + theories A B C T\n"}
    for name in "ABC":
        files[f"{name}.thy"] = (
            f"theory {name} imports Main begin\ntext \\<open>t\\<close>\n"
            f'definition {name.lower()}_c :: nat where "{name.lower()}_c = 0"\nend\n'
        )
    files["T.thy"] = (
        "theory T imports A B C begin\ntext \\<open>t\\<close>\n"
        'definition t_c :: nat where "t_c = a_c"\nend\n'
    )
    base = make_project(files)
    monkeypatch.chdir(base)
    monkeypatch.setattr(check_cli, "_MAX_ROUNDS", 1)
    # Unused imports go one per round, so one is left for a next run.
    assert main(["check", "unused", "--fix=all", "T.thy"]) == 1
    out, err = capsys.readouterr()
    assert out.count("unused-import") == 1
    assert err.startswith("fixed 1 finding\n")
