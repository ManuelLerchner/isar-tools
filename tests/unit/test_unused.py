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
            "ROOT": "session S = HOL + theories A B C D E F T U\n",
            "A.thy": 'theory A imports Main begin definition a_const where "a_const = 0" end',
            "B.thy": 'theory B imports A begin definition b_const where "b_const = 0" end',
            "C.thy": (
                'theory C imports Main begin definition c_const where "c_const = 0" '
                'lemma c_plain: "True" by simp locale c_loc begin lemma c_in: "True" by simp end '
                "end"
            ),
            "D.thy": 'theory D imports Main begin lemma d_rule [simp]: "True" by simp end',
            "E.thy": "theory E imports Main begin end",
            "F.thy": "theory F imports Main begin ML \\<open>\\<close> end",
            "U.thy": "theory U imports C F begin end",
            "NoHeader.thy": 'lemma "True" by simp',
            "T.thy": (
                "theory T\n  imports A B C D E F\nbegin\n"
                'lemma "b_const = a_const" using d_unrelated by simp\nend\n'
            ),
        }
    )
    paths = [base / "T.thy", base / "U.thy", base / "NoHeader.thy"]
    findings = [f for f in check_unused(collect(paths)) if f.code != "unused-lemma"]
    assert [(f.path.name, f.line, f.column, f.code, f.message) for f in findings] == [
        ("T.thy", 2, 11, "redundant-import", "A is imported through B already"),
        ("T.thy", 2, 15, "unused-import", "imports C, but nothing uses what it adds"),
        ("T.thy", 2, 19, "unused-import", "imports E, but nothing uses what it adds"),
        ("U.thy", 1, 18, "unused-import", "imports C, but nothing uses what it adds"),
    ]


def test_assumptions(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": r"""theory T imports Main begin
locale loc =
  fixes f :: "nat \<Rightarrow> nat"
  assumes cited_a: "f 0 = 0" and spare_a: "f 1 = 1" and simp_a [simp]: "f 2 = 2"
    and "f 3 = 3"
lemma (in loc) "f 0 = 0" by (rule cited_a)
locale whole =
  fixes g :: nat
  assumes spare_w: "g = 0"
lemma (in whole) "True" using whole_axioms by simp
class cls =
  fixes c :: 'a
  assumes spare_c: "c = c"
end
""",
        }
    )
    findings = check_unused(collect([base / "T.thy"]))
    assert [(f.line, f.message) for f in findings if f.code == "unused-assumption"] == [
        (4, "assumption spare_a of locale loc is cited nowhere; the locale may assume less"),
        (13, "assumption spare_c of class cls is cited nowhere; the class may assume less"),
    ]


def test_imports_after_the_redundant_ones(make_project: MakeProject) -> None:
    """An import that others reach through is used once they are gone, and an
    import serves the theories that import its importer."""
    base = make_project(
        {
            "ROOT": "session S = HOL + theories P Q R U V\n",
            "P.thy": 'theory P imports Main begin definition p_const where "p_const = 0" end',
            "Q.thy": "theory Q imports P begin end",
            "R.thy": 'theory R imports Main begin definition r_const where "r_const = 0" end',
            "U.thy": "theory U imports R begin end",
            "V.thy": 'theory V imports P Q U begin lemma "p_const = r_const" sorry end',
        }
    )
    findings = check_unused(collect([base / "U.thy", base / "V.thy"]))
    imports = [(f.path.name, f.code, f.message) for f in findings if "import" in f.code]
    assert imports == [("V.thy", "redundant-import", "P is imported through Q already")]
