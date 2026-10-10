from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import MakeProject

BASE = r"""theory Base imports Main begin
consts gamma :: "'a \<Rightarrow> int set" ("\<gamma> _" [1000] 1000)
consts eval :: "'e \<Rightarrow> 's \<Rightarrow> int" ("\<lbrakk>_\<rbrakk>\<^sub>e")
syntax "_imp" :: "'a \<Rightarrow> 'b" ("imp \<lbrakk> _ \<rbrakk>")
consts other :: "'a \<Rightarrow> 'a \<Rightarrow> nat" ("\<lbrakk>_|_\<rbrakk>")
end
"""
USES = r"""theory T imports Base begin
lemma "x \<in> \<lbrakk>d\<rbrakk>" "C \<lbrakk>d\<rbrakk> = y"
  "\<lbrakk>f a\<rbrakk> = \<lbrakk>(g b)\<rbrakk>"
  "\<lbrakk>\<lbrakk>a\<rbrakk>\<rbrakk> = z" "\<lbrakk>d\<rbrakk> \<union> \<lbrakk>e\<rbrakk> = s"
  "\<lbrakk>e\<rbrakk>\<^sub>e s = 0" "imp \<lbrakk> x \<rbrakk> = y"
  "\<lbrakk>A; B\<rbrakk> \<Longrightarrow> C"
  "\<lbrakk>a | b\<rbrakk> = 0"
  sorry
text \<open>\<lbrakk>d\<rbrakk>\<close>
end
"""
RENOTATED = r"""theory T imports Base begin
lemma "x \<in> \<gamma> d" "C (\<gamma> d) = y"
  "\<gamma> (f a) = \<gamma> (g b)"
  "\<gamma> (\<gamma> a) = z" "\<gamma> d \<union> \<gamma> e = s"
  "\<lbrakk>e\<rbrakk>\<^sub>e s = 0" "imp \<lbrakk> x \<rbrakk> = y"
  "\<lbrakk>A; B\<rbrakk> \<Longrightarrow> C"
  "\<lbrakk>a | b\<rbrakk> = 0"
  sorry
text \<open>\<lbrakk>d\<rbrakk>\<close>
end
"""
# A theory the constant is unknown in, and a generated one.
LOOSE = 'theory Loose imports Main begin\nlemma "\\<lbrakk>d\\<rbrakk> = x" sorry\nend\n'
FROM = ["--from", r'("\<lbrakk>_\<rbrakk>")']


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories Base T Loose Gen",
            "Base.thy": BASE,
            "T.thy": USES,
            "Loose.thy": LOOSE,
            "Gen.thy": USES.replace("theory T", "theory Gen"),
        }
    )
    monkeypatch.chdir(base)
    return base


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, list[str]]:
    status = main(["project", "renotate", *args])
    captured = capsys.readouterr()
    return status, captured.out, captured.err.splitlines()


def test_renotate(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err = run(capsys, "gamma", *FROM, "--check", "--exclude", "Gen.thy")
    assert (status, out, err) == (1, "T.thy\n", [])
    status, out, _ = run(
        capsys, "gamma", *FROM, "--diff", "--exclude", "Gen.thy", "--color", "never"
    )
    assert status == 1
    assert '+lemma "x \\<in> \\<gamma> d"' in out
    status, out, err = run(capsys, "gamma", *FROM, "--exclude", "Gen.thy")
    assert (status, out, err) == (0, "", ["renotated 7 terms in T.thy"])
    assert (project / "T.thy").read_text() == RENOTATED
    assert (project / "Loose.thy").read_text() == LOOSE
    assert (project / "Gen.thy").read_text() == USES.replace("theory T", "theory Gen")
    assert run(capsys, "gamma", "T.thy", *FROM, "--check") == (0, "", [])


def test_arguments(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T",
            "T.thy": r"""theory T imports Main begin
consts ev :: "'e \<Rightarrow> 's \<Rightarrow> int"
  ("\<lbrakk>_\<rbrakk>\<^sup>\<sharp> _" [0, 1000] 1000)
consts get :: "'s \<Rightarrow> 'x \<Rightarrow> int" ("\<G> _")
consts op :: "int \<Rightarrow> int \<Rightarrow> int" (infixl "\<otimes>" 70)
definition rsem :: "nat \<Rightarrow> nat \<Rightarrow> nat set" where "rsem r v = {r, v}"
syntax "_rsem" :: "nat \<Rightarrow> nat \<Rightarrow> nat set" ("\<rho>\<^bsub>_\<^esub>'(_')")
translations "\<rho>\<^bsub>v\<^esub>(r)" == "CONST rsem r v"
lemma "\<lbrakk>e\<rbrakk> d = 0" "f \<lbrakk>e\<rbrakk> = 0"
  "s\<langle>x\<rangle> = 0" "a \<oplus> b = c" "[a, b]"
  "R a b = {}"
  sorry
end
""",
        }
    )
    monkeypatch.chdir(base)
    assert run(capsys, "ev", *FROM)[2] == [
        "isar project renotate: left as written: T.thy:9: too few arguments for "
        r"\<lbrakk>_\<rbrakk>\<^sup>\<sharp> _",
        "renotated 1 terms in T.thy",
    ]
    assert run(capsys, "get", "--from", r'"_\<langle>_\<rangle>" [1000, 0] 1000')[0] == 0
    assert run(capsys, "op", "--from", r'infixl "\<oplus>" 65')[0] == 0
    assert run(capsys, "rsem", "--from", "R _ _")[0] == 0
    assert (base / "T.thy").read_text().splitlines()[8:11] == [
        r'lemma "\<lbrakk>e\<rbrakk>\<^sup>\<sharp> d = 0" "f \<lbrakk>e\<rbrakk> = 0"',
        r'  "(\<G> s) x = 0" "(a \<otimes> b) = c" "[a, b]"',
        r'  "\<rho>\<^bsub>b\<^esub>(a) = {}"',
    ]


def test_several_notations(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T",
            "T.thy": r"""theory T imports Main begin
locale a = fixes op :: "nat \<Rightarrow> nat" ("\<alpha> _")
locale b = fixes op :: "nat \<Rightarrow> nat" ("\<beta> _")
locale c = fixes op :: "nat \<Rightarrow> nat" ("\<lbrakk>_\<rbrakk>")
locale ab = a + b
lemma (in a) "\<lbrakk>x\<rbrakk> = 0" sorry
lemma (in ab) "\<lbrakk>x\<rbrakk> = 0" sorry
lemma (in c) "\<lbrakk>x\<rbrakk> = 0" sorry
end
""",
        }
    )
    monkeypatch.chdir(base)
    status, _, err = run(capsys, "op", *FROM)
    assert (status, err) == (
        0,
        [
            "isar project renotate: left as written: T.thy:7: it has several "
            r"notations: \<alpha> _, \<beta> _",
            "renotated 1 terms in T.thy",
        ],
    )
    assert r'lemma (in a) "(\<alpha> x) = 0"' in (base / "T.thy").read_text()


def test_invalid(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "eval", "--from", "(infixl 65)")[2] == [
        "isar project: --from: no notation in ((infixl 65))"
    ]
    assert run(capsys, "eval", "--from", r'(binder "\<lbrakk>" 10)')[2] == [
        r'isar project: --from: the mixfix (binder "\<lbrakk>" 10) is not supported'
    ]
    assert run(capsys, "eval", "--from", "_")[2] == [
        'isar project: the notation "_" is not supported'
    ]
    assert run(capsys, "nothing", *FROM)[2] == [
        r'isar project: nothing has no notation other than "\<lbrakk>_\<rbrakk>"'
    ]


def test_edge_cases(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T",
            "T.thy": r"""theory T imports Main begin
consts op :: "int \<Rightarrow> int \<Rightarrow> int" ("\<O> _ _" [1000, 1000] 1000)
consts sq :: "int \<Rightarrow> int" ("\<lfloor>_\<rfloor>")
lemma "\<oplus> b" "(a) \<oplus> b" "f a \<oplus> b" "x) \<oplus> b"
lemma "\<lbrakk>f \<lbrakk>a\<rbrakk>\<rbrakk>" "\<lbrakk>a) b\<rbrakk>"
end
""",
        }
    )
    monkeypatch.chdir(base)
    assert run(capsys, "op", "--from", r'infixl "\<oplus>" 65')[0] == 0
    assert run(capsys, "sq", *FROM)[0] == 0
    assert run(capsys, "sq", "--from", "_ _")[0] == 0
    assert (base / "T.thy").read_text().splitlines()[3:5] == [
        r'lemma "\<oplus> b" "\<O> (a) b" "f a \<oplus> b" "x) \<oplus> b"',
        r'lemma "\<lfloor>f \<lfloor>a\<rfloor>\<rfloor>" "\<lbrakk>a) b\<rbrakk>"',
    ]
    assert run(capsys, "sq", "--from", r'"\<lbrakk>_\<rbrakk>\<index>"')[2] == [
        r'isar project: the notation "\<lbrakk>_\<rbrakk>\<index>" is not supported'
    ]
