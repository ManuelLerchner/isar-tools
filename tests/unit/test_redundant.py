from isar_tools.checks.redundant import check_redundant
from isar_tools.project.workspace import collect
from tests.conftest import MakeProject

BASE = r"""theory Base imports Main begin
definition step :: "nat \<Rightarrow> nat \<Rightarrow> nat" where "step a b = a"
consts gamma :: "'a \<Rightarrow> nat set" ("\<gamma>")
lemma general: assumes "x \<le> y" shows "step x z \<le> step y z" sorry
lemma rule_premise:
  assumes "\<And>q. q \<in> set qs \<Longrightarrow> f q = 0"
  shows "foldr step qs 0 = 0" sorry
locale loc = fixes k :: nat
lemma (in loc) in_loc: "step k k = k" sorry
end
"""
T = r"""theory T imports Base begin
lemma renamed: "a \<le> b \<Longrightarrow> step a c \<le> step b c" sorry
lemma special: "n \<le> m \<Longrightarrow> step n (Suc 0) \<le> step m (Suc 0)" sorry
lemma more_premises:
  "\<lbrakk>P; a \<le> b\<rbrakk> \<Longrightarrow> step a c \<le> step b c" sorry
lemma constant_differs: "a \<le> b \<Longrightarrow> step c a \<le> step b c" sorry
lemma split_rule: assumes "q \<in> set qs" "f q = 0" shows "foldr step qs 0 = 0" sorry
lemma literal_1: "f ''w'' = 1" sorry
lemma literal_2: "f ''z'' = 1" sorry
lemma numeral_1: "f 1 = (2::nat)" sorry
lemma numeral_2: "f 3 = (2::nat)" sorry
lemma outside_loc: "step k k = k" sorry
lemma notation_is_constant: "\<gamma> x = gamma_int x" sorry
lemma notation_is_constant2: "f x = gamma_int x" sorry
lemma registered [simp]: "a \<le> b \<Longrightarrow> step a c \<le> step b c" sorry
end
"""


def test_redundant(make_project: MakeProject) -> None:
    base = make_project(
        {"ROOT": "session S = HOL + theories Base T\n", "Base.thy": BASE, "T.thy": T}
    )
    findings = check_redundant(collect([base / "T.thy"]))
    assert [(f.line, f.code, f.message) for f in findings] == [
        (2, "duplicate-lemma", "renamed states general (Base.thy:4) again"),
        (3, "subsumed-lemma", "special is an instance of general (Base.thy:4); cite it instead"),
        (
            4,
            "subsumed-lemma",
            "more_premises is an instance of general (Base.thy:4); cite it instead",
        ),
    ]
