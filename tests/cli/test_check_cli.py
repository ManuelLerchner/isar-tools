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
    assert err == "3 findings: 2 document-argument, 1 unfinished-proof\n"
    golden("check/default.txt", out)


def test_group_and_ignore(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "symbols", "A.thy")
    assert status == 1
    assert out.startswith("A.thy:2:13: non-ascii: non-ASCII character '⟹'")
    status, out, err = run(capsys, "symbols", "A.thy", "--ignore", "non-ascii")
    assert (status, out, err) == (0, "", "no findings\n")


def test_project_group_and_include(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "--group", "project", ".")
    assert status == 1
    assert out.splitlines() == [
        "ROOT:1:31: missing-directory: no directory gone for session S",
    ]
    status, out, _ = run(capsys, "--group", "syntax", "B.thy")
    assert status == 1
    assert "unexpected 'libcmd' after the text of text" in out
    assert "pass its directory with -d" in out
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


def test_color_and_singular_summary(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err = run(capsys, "--group", "proofs", "--color", "always", "A.thy")
    assert status == 1
    assert out == (
        "\x1b[1mA.thy\x1b[0m\x1b[2m:2:18:\x1b[0m \x1b[33;1munfinished-proof\x1b[0m: "
        "sorry leaves the goal unproved\n"
    )
    assert err == "1 finding: 1 unfinished-proof\n"


def test_locales_group(
    make_project: MakeProject,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    golden: Golden,
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories L",
            "L.thy": "theory L imports Main begin\n"
            "locale l = fixes own_op\n"
            '  assumes "own_op = enter_local" and "\\<forall>bound_var. own_op bound_var"\n'
            "end\n",
        }
    )
    monkeypatch.chdir(base)
    assert run(capsys, ".") == (0, "", "no findings\n")  # not a default group
    status, out, err = run(capsys, "locales", ".")
    assert (status, err) == (1, "1 finding: 1 locale-free-variable\n")
    golden("check/locales.txt", out)
    assert run(capsys, "locales", ".", "--allow", "enter_local") == (0, "", "no findings\n")


def test_nested_project_is_skipped_with_a_note(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories A",
            "A.thy": "theory A imports Main begin end",
            "vendor/lib/ROOT": "session L = HOL + theories B",
            "vendor/lib/B.thy": "theory B imports Main begin lemma x: True sorry end",
        }
    )
    monkeypatch.chdir(base)
    assert main(["check", "."]) == 0
    assert "note: skipped vendor/lib: another project" in capsys.readouterr().err
    assert main(["check", "-d", "vendor/lib", "."]) == 0
    assert "note" not in capsys.readouterr().err


def test_configuration_file(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = make_project(
        {
            "pyproject.toml": '[tool.isar.check]\ngroups = ["proofs"]\nignore = ["oops"]\n',
            "ROOT": "session S = HOL + theories A Missing",
            "A.thy": "theory A imports Main begin\nlemma x: True sorry\nlemma y: True oops\nend\n",
        }
    )
    monkeypatch.chdir(base)
    # Only the proofs group (no missing-theory), and oops ignored.
    assert main(["check", "--format", "json", "."]) == 1
    codes = [f["code"] for f in json.loads(capsys.readouterr().out)["findings"]]
    assert codes == ["unfinished-proof"]
    # --group on the command line replaces the file's groups.
    assert main(["check", "--group", "project", "--format", "json", "."]) == 1
    codes = [f["code"] for f in json.loads(capsys.readouterr().out)["findings"]]
    assert codes == ["missing-theory"]


def test_new_groups_and_invalid_utf8(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories A B",
            "A.thy": "theory A imports Main begin\nlemma x: True\n\tsledgehammer\n  by simp\nend\n",
            "B.thy": "",
        }
    )
    # Bytes, not text: on Windows write_text would add CRs, which hygiene reports.
    (base / "A.thy").write_bytes(
        b"theory A imports Main begin\nlemma x: True\n\tsledgehammer\n  by simp\nend\n"
    )
    (base / "B.thy").write_bytes(b"theory B imports Main begin\n\xff\nend\n")
    monkeypatch.chdir(base)
    assert main(["check", "--format", "json", "."]) == 1
    found = [(f["path"], f["code"]) for f in json.loads(capsys.readouterr().out)["findings"]]
    assert found == [("B.thy", "invalid-utf8")]
    args = ["check", "--group", "hygiene", "--group", "leftovers", "--format", "json", "."]
    assert main(args) == 1
    found = [(f["path"], f["code"]) for f in json.loads(capsys.readouterr().out)["findings"]]
    assert found == [("A.thy", "tab"), ("A.thy", "proof-search")]


def test_several_positional_groups() -> None:
    from isar_tools.checks.cli import normalize_argv

    assert normalize_argv(["check", "leftovers", "hygiene", "src"]) == [
        "check",
        "--group",
        "leftovers",
        "--group",
        "hygiene",
        "src",
    ]
    assert normalize_argv(["fmt", "docs"]) == ["fmt", "docs"]
