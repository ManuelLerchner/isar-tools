from pathlib import Path

import pytest

from isar_tools.checks.prose import scan
from isar_tools.cli import main
from tests.conftest import MakeProject


def test_scan_references_and_underscores() -> None:
    text = (
        r"\<open>Uses \<open>f_def\<close>, \<^const>\<open>g_h\<close>,"
        r" @{thm a_b [of \<open>c_d\<close>]},"
        r" x\<^sub>1, ‹loc.fact_x›, \<open>not a name\<close> and raw_prose\<close>"
    )
    references, underscores = scan(text, 100)
    assert [(r.name, r.offset - 100) for r in references] == [
        ("f_def", text.index("f_def")),
        ("loc.fact_x", text.index("loc.fact_x")),
    ]
    assert [u - 100 for u in underscores] == [text.index("raw_prose") + 3]


def test_scan_unclosed_antiquotation() -> None:
    assert scan(r"\<open>@{thm a_b\<close>", 0) == ([], [])


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories A B",
            "A.thy": "theory A imports Main begin\n"
            'definition some_const :: nat where "some_const = map_of [] (0::nat)"\n'
            "locale my_loc = assumes my_ax: True\n"
            "end\n",
            "B.thy": "theory B imports A begin\n"
            "text \\<open>\\<open>some_const_def\\<close> \\<open>map_of\\<close> "
            "\\<open>my_loc.my_ax\\<close> \\<open>A.some_const\\<close> "
            "\\<open>q.some_const_def\\<close> \\<open>gone_name\\<close> "
            "\\<open>goblint_id\\<close> \\<open>abc\\<close>\\<close>\n"
            "section \\<open>With raw_underscore\\<close>\n"
            'text "a string_argument"\n'
            "interpretation q: my_loc by simp\ntext_raw \\<open>raw_ok\\<close>\n"
            "(* \\<open>in_comment\\<close> *)\n"
            'lemma "True" \\<comment> \\<open>about \\<open>other_gone\\<close>\\<close> by simp\n'
            "end\n",
        }
    )
    monkeypatch.chdir(base)
    return base


def test_prose_check(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", "prose", "B.thy", "--allow", "goblint_id"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "B.thy:2:160: prose-reference: gone_name names no declaration of the project",
        "B.thy:3:24: prose-underscore: raw _ in document prose reaches LaTeX unescaped; "
        "cite the name in a cartouche or an antiquotation",
    ]
