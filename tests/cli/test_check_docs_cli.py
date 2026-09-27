from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import Golden, MakeProject

THEORY = """\
theory T imports Main begin
section \\<open>Setting\\<close>
locale l = fixes x :: nat
text \\<open>Documented.\\<close>
subsection \\<open>Facts\\<close>
lemma "True" sorry
end
"""


def test_docs_group_is_opt_in(
    make_project: MakeProject,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    golden: Golden,
) -> None:
    monkeypatch.chdir(make_project({"T.thy": THEORY}))
    status = main(["check", "docs", "T.thy"])
    out, err = capsys.readouterr()
    assert status == 1
    assert (
        err == "3 findings: 1 undocumented-heading, 1 undocumented-locale, 1 undocumented-theory\n"
    )
    golden("check/docs.txt", out)
    assert main(["check", "T.thy"]) == 1
    assert "undocumented" not in capsys.readouterr().out
    assert main(["check", "--group", "docs", "--ignore", "undocumented-theory", "T.thy"]) == 1
    assert "undocumented-theory" not in capsys.readouterr().out


def test_documented_file_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "T.thy").write_text("theory T imports Main begin\ntext \\<open>t\\<close>\nend\n")
    monkeypatch.chdir(tmp_path)
    assert main(["check", "docs", "T.thy"]) == 0
    assert capsys.readouterr() == ("", "no findings\n")
