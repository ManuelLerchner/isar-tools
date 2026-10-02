from isar_tools.checks.redundant import Statement, check_redundant, instance, split_prop, statement
from isar_tools.checks.terms import spelling, term_tokens
from isar_tools.project.workspace import collect
from isar_tools.source.lexer import tokenize
from isar_tools.source.theory import significant
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
locale loc2 = loc
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
lemma "quoted": obtains x where "x = 0" sorry
lemma (in loc2) in_loc2: "step k k = k" sorry
lemma "far_general": "far x" sorry
end
"""


def test_redundant(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories Base Other T\n",
            "Base.thy": BASE,
            "Other.thy": 'theory Other imports Main begin lemma far: "far y" sorry end',
            "T.thy": T,
        }
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
        (17, "duplicate-lemma", "in_loc2 states in_loc (Base.thy:9) again"),
    ]


def _statement(text: str, constants: frozenset[str] = frozenset()) -> Statement | None:
    return statement(list(significant(tokenize(text))), constants)


def test_split_prop() -> None:
    def split(text: str) -> tuple[list[str], str, set[str]]:
        premises, conclusion, variables = split_prop(term_tokens(text))
        return [" ".join(spelling(p)) for p in premises], " ".join(spelling(conclusion)), variables

    assert split(r"(\<And>x y. (A x) \<Longrightarrow> B)") == (["A x"], "B", {"x", "y"})
    assert split("(a) + (b)") == ([], "( a ) + ( b )", set())
    assert split(r"\<lbrakk>x\<rbrakk> = y") == ([], r"\<lbrakk> x \<rbrakk> = y", set())


def test_statement() -> None:
    assert _statement('obtains x where "P x"') is None
    assert _statement('shows "A" "B"') is None
    assert _statement('"\\<lbrakk>A\\<rbrakk> \\<Longrightarrow> ()"') is None
    found = _statement('fixes x :: "nat" and long_name shows "P x long_name ?z 1 c"')
    assert found is not None
    assert found.variables == {"x", "long_name", "?z", "P", "c"}
    assert _statement('"A \\<Longrightarrow> "') is None


def test_instance_premises() -> None:
    general = _statement('assumes "P x" "Q x" shows "R x"', frozenset({"P", "Q", "R"}))
    special = _statement('assumes "Q a" "S" "P a" shows "R a"', frozenset({"P", "Q", "R", "S"}))
    other = _statement('assumes "P a" shows "R a"', frozenset({"P", "Q", "R"}))
    trivial = _statement('"x"')
    assert general is not None
    assert special is not None
    assert other is not None
    assert trivial is not None
    assert instance(general, special)
    assert not instance(general, other)
    assert not instance(trivial, special)
