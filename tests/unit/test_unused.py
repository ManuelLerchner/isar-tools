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
lemma "quoted": "True" by simp
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
        (18, "lemma quoted is cited nowhere in the project"),
    ]


def test_allow(make_project: MakeProject) -> None:
    lines = [line for line, _ in found(make_project, "inert", "Base.uses")]
    assert lines == [4, 7, 13, 17, 18]


def test_antiquotations() -> None:
    text = r"a @{thm x[of {y}]} b \<^const>\<open>c \<open>d\<close>\<close> e \<^emph> f"
    assert [text[a:b] for a, b in antiquotations(text)] == [
        "@{thm x[of {y}]}",
        r"\<^const>\<open>c \<open>d\<close>\<close>",
    ]
    assert list(antiquotations("@{thm x")) == [(0, 7)]
    assert list(antiquotations(r"\<^const>\<open>c")) == [(0, 17)]


def test_imports(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories A B C D E T\n",
            "A.thy": 'theory A imports Main begin definition a_const where "a_const = 0" end',
            "B.thy": 'theory B imports A begin definition b_const where "b_const = 0" end',
            "C.thy": 'theory C imports Main begin definition c_const where "c_const = 0" end',
            "D.thy": 'theory D imports Main begin lemma d_rule [simp]: "True" by simp end',
            "E.thy": "theory E imports Main begin end",
            "T.thy": (
                "theory T\n  imports A B C D E\nbegin\n"
                'lemma "b_const = a_const" using d_unrelated by simp\nend\n'
            ),
        }
    )
    findings = check_unused(collect([base / "T.thy"]))
    assert [(f.line, f.column, f.code, f.message) for f in findings] == [
        (2, 11, "redundant-import", "A is imported through B already"),
        (2, 15, "unused-import", "imports C, but uses nothing it adds"),
        (2, 19, "unused-import", "imports E, but uses nothing it adds"),
    ]
