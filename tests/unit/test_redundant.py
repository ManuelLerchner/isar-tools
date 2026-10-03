import pytest

from isar_tools.checks.redundant import Statement, check_redundant, instance, split_prop, statement
from isar_tools.checks.terms import spelling, term_tokens
from isar_tools.project.workspace import collect
from isar_tools.source.lexer import tokenize
from isar_tools.source.theory import significant
from tests.conftest import MakeProject


def test_contract_assumption_cannot_prove_its_interpretation(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories Contract Instance\n",
            "Contract.thy": """theory Contract imports Main begin
locale contract = fixes gamma :: "nat => nat" assumes monotone: "mono gamma"
context fixes g :: "nat => nat" assumes valid: "contract g" begin
lemma unit_gammaDG_mono: "mono g"
  using valid by (simp add: contract_def)
end
end
""",
            "Instance.thy": """theory Instance imports Contract begin
definition gammaDG_relc :: "nat => nat" where "gammaDG_relc x = x"
lemma gammaDG_relc_mono: "mono gammaDG_relc"
  by (simp add: gammaDG_relc_def mono_def)
interpretation concrete: contract gammaDG_relc
  by standard (rule gammaDG_relc_mono)
end
""",
        }
    )
    assert not check_redundant(collect([base / "Instance.thy"]))


@pytest.mark.parametrize(
    "header",
    [
        'context fixes g :: "nat => nat" assumes contract: "mono g" begin',
        'context assumes contract: "mono g" begin',
        'context L assumes contract: "mono g" begin',
        "context includes configured begin",
        "context begin",
        "instantiation nat :: order begin",
    ],
)
@pytest.mark.parametrize("sibling", [False, True])
def test_context_boundaries(make_project: MakeProject, header: str, sibling: bool) -> None:
    target = 'lemma target: "mono g" sorry\n'
    if sibling:
        target = f"{header}\n{target}end\n"
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": 'theory T imports Main begin\nlocale L = fixes g :: "nat => nat"\n'
            f'{header}\nlemma general: "mono g" sorry\nend\n{target}end\n',
        }
    )
    assert not check_redundant(collect([base]))


def test_nested_contexts_and_named_locale_reopening(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": """theory T imports Main begin
locale L = fixes g :: "nat => nat" begin
context assumes contract: "mono g" begin
lemma general: "mono g" sorry
lemma same_block: "mono g" sorry
context assumes extra: "True" begin
lemma nested: "mono g" sorry
end
lemma back_in_outer: "mono g" sorry
end
lemma outside_assumptions: "mono g" sorry
end
context L begin
lemma reopened: "mono g" sorry
end
end
""",
        }
    )
    found = check_redundant(collect([base]))
    assert [f.message.split()[0] for f in found] == [
        "same_block",
        "nested",
        "back_in_outer",
        "reopened",
    ]
    # Reopening the locale sees only the lemma outside the extra assumptions.
    assert "states outside_assumptions" in found[-1].message


def test_global_fact_remains_available_inside_context(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": """theory T imports Main begin
lemma general: "mono g" sorry
context assumes extra: "True" begin
lemma inside: "mono g" sorry
end
end
""",
        }
    )
    found = check_redundant(collect([base]))
    assert len(found) == 1
    assert found[0].message.startswith("inside states general")


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
lemma k_is_free: "k \<le> m \<Longrightarrow> step k c \<le> step m c" sorry
lemma q_is_free: "q \<le> m \<Longrightarrow> step q c \<le> step m c" sorry
end
"""


def test_redundant(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories Base Other T\n",
            "Base.thy": BASE,
            "Other.thy": (
                'theory Other imports Main begin lemma far: "far y" sorry consts q :: nat end'
            ),
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
        # `k` is a parameter of `loc` only: outside it, a variable.
        (19, "duplicate-lemma", "k_is_free states general (Base.thy:4) again"),
        # `q` is a constant of Other, which T does not import.
        (20, "duplicate-lemma", "q_is_free states general (Base.thy:4) again"),
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
