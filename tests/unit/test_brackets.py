from isar_tools.checks.notation import check_notation
from isar_tools.project.workspace import collect
from tests.conftest import MakeProject

HEADER = r"""theory T imports Main begin
definition lo :: "nat \<Rightarrow> nat \<Rightarrow> nat" (infixl "\<oplus>" 65) where "lo a b = a"
definition hi :: "nat \<Rightarrow> nat \<Rightarrow> nat" (infixl "\<otimes>" 1000)
  where "hi a b = a"
definition call :: "nat \<Rightarrow> nat \<Rightarrow> nat" ("CALL _ _" [0, 0] 10)
  where "call a b = a"
syntax "_post" :: "nat \<Rightarrow> nat" ("_ \<dagger>" [1000] 1000)
syntax "_wrap" :: "nat \<Rightarrow> nat" ("WRAP'(_')")
"""


def found(make_project: MakeProject, body: str) -> list[tuple[int, str, str]]:
    base = make_project(
        {"ROOT": "session S = HOL + theories T\n", "T.thy": f"{HEADER}{body}\nend\n"}
    )
    return [
        (f.line - HEADER.count("\n"), f.message.split(" needs")[0], f.fix.edits[0].text)
        for f in check_notation(collect([base / "T.thy"]))
        if f.code == "redundant-brackets" and f.fix
    ]


def test_reported(make_project: MakeProject) -> None:
    body = r"""lemma "(reaching ds p v) \<subseteq> (\<Union>ctx. f ctx)" "g (x) ((a + b)) ([a])"
lemma "if (f x) then (g y) else h z" "\<forall>x. (P x)"
  "\<lbrakk>(P x); Q\<rbrakk> \<Longrightarrow> R"
lemma "(f x) :: nat" "(f x) \<oplus> y" "f(x) = y" "\<lbrakk>(a) + b\<rbrakk>" "-(- a)" """
    assert found(make_project, body) == [
        (1, "(reaching ds p v)", "reaching ds p v"),
        (1, "(x)", "x"),
        (1, "((a + b))", "(a + b)"),
        (1, "([a])", "[a]"),
        (2, "(f x)", "f x"),
        (2, "(g y)", "g y"),
        (2, "(P x)", "P x"),
        (3, "(P x)", "P x"),
        (4, "(f x)", "f x"),
        (4, "(f x)", "f x"),
        (4, "(x)", " x"),
        (4, "(a)", "a"),
    ]


def test_needed(make_project: MakeProject) -> None:
    body = r"""lemma "g (f x)" "(f x) y" "(a + b) * c" "(a, b)" "()" "(-)" "(div) a"
lemma "a * (n choose k)" "(f x)\<^sup>*" "x\<^sub>(i)" "(f x) \<le>\<^sub>r y" "(f x) \<otimes> y"
lemma "(CALL f x) = y" "(CALL)" "(f x) \<dagger>" "(h (f x" "(\<lambda>x. x) = f" "(_)"
lemma "TYPE('a) = t" "CALL (f x) y" "WRAP(x) = y" """
    assert found(make_project, body) == []


def test_brackets_after_a_slot(make_project: MakeProject) -> None:
    # A notation that follows an argument with `(` may own any such brackets.
    body = r"""syntax "_fn" :: "nat \<Rightarrow> nat \<Rightarrow> nat" ("FN _'(_')")
lemma "FN f(x) = y" "g (x) = (f x)" """
    assert found(make_project, body) == [(2, "(f x)", "f x")]
