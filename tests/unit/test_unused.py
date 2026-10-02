from isar_tools.checks.unused import antiquotations, check_unused
from isar_tools.project.workspace import collect
from tests.conftest import MakeProject

ROOT = "session S = HOL + theories Base T\n"
BASE = r"""theory Base imports Main begin
lemma cited_later: "True" by simp
lemma cited_by_t: "True" by simp
lemma own_proof_only: "True" using own_proof_only by simp
lemma registered [simp]: "True" by simp
lemma inert [rule_format]: "True" by simp
lemmas renamed = cited_later
locale loc begin
lemma in_locale: "True" by simp
end
interpretation q: loc .
lemma in_text: "True" by simp
lemma in_prose: "True" by simp
text \<open>See @{thm in_text}, not \<open>in_prose\<close>.\<close>
lemma uses: "True" using cited_later by simp
(* commented_out is cited nowhere *)
lemma commented_out: "True" by simp
end
"""
T = r"""theory T imports Base begin
lemma "True" using cited_by_t q.in_locale by simp
end
"""


def found(make_project: MakeProject, *allow: str) -> list[tuple[int, str]]:
    base = make_project({"ROOT": ROOT, "Base.thy": BASE, "T.thy": T})
    findings = check_unused(collect([base / "Base.thy"]), allow=allow)
    return [(f.line, f.message) for f in findings]


def test_unused_lemmas(make_project: MakeProject) -> None:
    assert found(make_project) == [
        (4, "lemma own_proof_only is cited nowhere in the project"),
        (6, "lemma inert is cited nowhere in the project"),
        (7, "lemmas renamed is cited nowhere in the project"),
        (13, "lemma in_prose is cited nowhere in the project"),
        (15, "lemma uses is cited nowhere in the project"),
        (17, "lemma commented_out is cited nowhere in the project"),
    ]


def test_allow(make_project: MakeProject) -> None:
    lines = [line for line, _ in found(make_project, "inert", "Base.uses")]
    assert lines == [4, 7, 13, 17]


def test_antiquotations() -> None:
    text = r"a @{thm x[of {y}]} b \<^const>\<open>c \<open>d\<close>\<close> e \<^emph> f"
    assert [text[a:b] for a, b in antiquotations(text)] == [
        "@{thm x[of {y}]}",
        r"\<^const>\<open>c \<open>d\<close>\<close>",
    ]
