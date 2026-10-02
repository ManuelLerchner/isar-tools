from isar_tools.checks.notation import check_notation
from isar_tools.project.workspace import collect
from tests.conftest import MakeProject

ROOT = "session S = HOL + theories Base T\n"
BASE = r"""theory Base imports Main begin
definition widen :: "'a \<Rightarrow> 'a \<Rightarrow> 'a" (infixl "\<nabla>" 65) where
  "widen a b = b"
definition get :: "'a \<Rightarrow> 'b \<Rightarrow> 'c" ("_\<langle>_\<rangle>" [1000, 0] 1000)
  where
  "get s x = undefined"
consts gamma :: "'s \<Rightarrow> 'a set" ("\<lbrakk>_\<rbrakk>")
definition gamma_int :: "int \<Rightarrow> int set" where "gamma_int i = {i}"
definition lift :: "('a \<Rightarrow> 'b) \<Rightarrow> 'a \<Rightarrow> 'b" where "lift f = f"
adhoc_overloading gamma == gamma_int and gamma == "lift gamma_int"
definition readback :: "'a \<Rightarrow> 'b \<Rightarrow> 'c" where "readback g s = undefined"
bundle syn
begin
notation readback ("\<rho>\<^bsub>_\<^esub>")
end
bundle outer
begin
unbundle syn
end
record r = fld :: nat ("\<phi>")
locale loc =
  fixes op :: "'a \<Rightarrow> 'a" ("\<omega>")
  assumes "op x = x"
class cls =
  fixes cop :: "'a \<Rightarrow> 'a" ("\<kappa>")
  assumes "cop x = x"
end
"""


def found(make_project: MakeProject, body: str, *allow: str) -> list[tuple[int, str]]:
    base = make_project(
        {"ROOT": ROOT, "Base.thy": BASE, "T.thy": f"theory T imports Base begin\n{body}\nend\n"}
    )
    findings = check_notation(collect([base / "T.thy"]), allow=allow)
    return [(f.line, f.message.split(" is written out")[0]) for f in findings]


def base_findings(make_project: MakeProject) -> list[tuple[int, str]]:
    base = make_project(
        {"ROOT": ROOT, "Base.thy": BASE, "T.thy": "theory T imports Base begin end"}
    )
    return [(f.line, f.message) for f in check_notation(collect([base / "Base.thy"]))]


def test_mixfix_and_infix(make_project: MakeProject) -> None:
    body = r"""lemma "widen a b = c" "foldr widen xs" "x\<langle>v\<rangle> = y"
lemma "get s v = get s" "f (get s v)"
lemma "g get s v" """
    assert found(make_project, body) == [
        (2, "widen"),
        (2, "widen"),  # infix: `(\<nabla>)` stands unapplied
        (3, "get"),  # `get s` lacks an argument for the notation
        (3, "get"),  # inside brackets, a name heads its own application
    ]


def test_message(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": ROOT,
            "Base.thy": BASE,
            "T.thy": 'theory T imports Base begin\nterm "widen a b"\nend\n',
        }
    )
    [finding] = check_notation(collect([base / "T.thy"]))
    assert finding.message == r"widen is written out; its notation is _ \<nabla> _"
    assert (finding.line, finding.column) == (2, 7)


def test_adhoc_overloading(make_project: MakeProject) -> None:
    body = r"""lemma "x \<in> gamma_int i" "lift gamma_int i = y" "P gamma_int"
lemma "map gamma_int xs" """
    assert found(make_project, body) == [(2, "gamma_int"), (2, "lift gamma_int")]


def test_unresolvable_overloading(make_project: MakeProject) -> None:
    # Bare partial applications and attribute terms give the generic name no type.
    body = r"""lemma "map (lift gamma_int) xs = ys" "f (gamma_int i) = y" "(gamma_int i) = y"
lemma "P" using foo[where g = "gamma_int"] bar[of "gamma_int"] by simp"""
    assert found(make_project, body) == [(2, "gamma_int")]


def test_bundles(make_project: MakeProject) -> None:
    body = r"""lemma "readback g s = x"
unbundle outer
lemma "readback g s = x"
unbundle no outer
lemma "readback g s = x"
context includes syn begin
lemma "readback g s = x"
end
lemma "readback g s = x" including syn by simp
lemma "readback g" """
    assert found(make_project, body) == [(4, "readback"), (8, "readback"), (10, "readback")]


def test_scopes_and_variables(make_project: MakeProject) -> None:
    body = r"""context loc begin
lemma "op x = x" by simp
end
lemma "op x = x"
lemma (in loc) "op x = x"
lemma "cop x = x" "fld r = 0" "r\<lparr>fld := 1\<rparr> = s" "\<lparr>fld = 1\<rparr> = s"
lemma "\<And>widen. widen a b" "widen a b" for widen
lemma "P x" proof (cases x)
  case (C widen)
  then show ?thesis using \<open>widen a b\<close> by simp
qed
text \<open>widen a b\<close>
ML \<open>widen a b\<close>"""
    assert found(make_project, body) == [(3, "op"), (6, "op"), (7, "cop"), (7, "fld")]


def test_declaring_command_and_order(make_project: MakeProject) -> None:
    # Own defining equations, and uses before the short form exists, are fine;
    # a locale's and a class's header already uses its parameters' mixfix.
    assert base_findings(make_project) == [
        (23, r"op is written out; its notation is \<omega>"),
        (26, r"cop is written out; its notation is \<kappa>"),
    ]


def test_local_notation(make_project: MakeProject) -> None:
    body = r"""context begin
notation lift ("\<L>")
lemma "lift f x = y"
end
lemma "lift f x = y"
notation (output) gamma_int ("\<G>")"""
    assert found(make_project, body) == [(4, "lift")]


def test_allow(make_project: MakeProject) -> None:
    assert found(make_project, 'lemma "widen a b = gamma_int i"', "widen") == [(2, "gamma_int")]


def test_declaration_forms(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories Lib Other T\n",
            "Lib.thy": r"""theory Lib imports Main begin
definition All2 :: "('a \<Rightarrow> bool) \<Rightarrow> bool" (binder "\<forall>\<forall>" 10)
  where "All2 P = All P"
consts hidden :: "'a \<Rightarrow> 'a"
private lemma priv: "True" by simp
consts ip :: "nat \<Rightarrow> nat" consts op2 :: "nat \<Rightarrow> nat"
notation (input) ip ("\<iota>") and op2 and hidden (binder "\<hh>" 10)
consts g :: "nat \<Rightarrow> nat" consts h :: "nat \<Rightarrow> nat"
adhoc_overloading g == h ""
bundle b1 begin notation op2 ("\<oo>") end
bundle b2 = b1
open_bundle b3 begin notation hidden ("\<hidden>") end
experiment begin notation h ("\<eta>") end
end
""",
            "Other.thy": r"""theory Other imports Main begin
consts far :: "nat" ("\<phi>\<phi>")
end
""",
            "T.thy": r"""theory T imports Lib begin
lemma "All2 P" "priv n = n" "ip n = 0" "h n = 0" "hidden n = 0" "far = 0" "h (Suc 0) = 0"
lemma "op2 n = 0" including b2 b1 sorry
lemma "\<And>x. x \<and> (h (f x) y z" "h (f x" for x and y sorry
end
""",
        }
    )
    findings = check_notation(collect([base / "T.thy"]))
    assert [(f.line, f.message) for f in findings] == [
        (2, r"ip is written out; its notation is \<iota>"),
        (2, "h is written out; it is overloaded as g"),
        (2, r"hidden is written out; its notation is \<hidden> (bundle b3)"),
        (2, "h is written out; it is overloaded as g"),
        (3, r"op2 is written out; its notation is \<oo> (bundle b1)"),
        (4, "h is written out; it is overloaded as g"),
        (4, "h is written out; it is overloaded as g"),
    ]


def test_one_line_theory(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories L T\n",
            "L.thy": r'theory L imports Main begin consts one :: nat ("\<one>") end',
            "T.thy": 'theory T imports L begin lemma "one = 0" sorry end',
        }
    )
    [finding] = check_notation(collect([base / "T.thy"]))
    assert finding.message == r"one is written out; its notation is \<one>"


def test_abbreviations(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": r"""theory T imports Main begin
definition step :: "nat \<Rightarrow> nat \<Rightarrow> nat" where "step a b = a"
abbreviation both where "both x y \<equiv> step x y + step y x"
abbreviation fwd where "fwd x \<equiv> step x (Suc x)"
abbreviation narrow where "narrow x y \<equiv> step x y"
abbreviation from_var where "from_var x \<equiv> x + 1"
context fixes k :: nat begin
abbreviation local_k where "local_k \<equiv> step k k"
lemma "step k k = 0" sorry
end
lemma "both a b = 0" "fwd 2 = 0" "c = step a b + step b a" "(step a b + step b a) = c"
lemma "step a b + step b a + c = 0" "fwd (f a) = step (f a) (Suc (f a))"
lemma "step k k = 0" "g fwd" "step a (Suc b) = 0"
end
""",
        }
    )
    findings = check_notation(collect([base / "T.thy"]))
    got = [(f.line, f.code, f.message.split(" is written out")[0]) for f in findings]
    assert got == [
        (9, "spelled-out-abbreviation", "step k k"),
        (11, "spelled-out-abbreviation", "step a b + step b a"),
        (12, "spelled-out-abbreviation", "step (f a) (Suc (f a))"),
    ]


def test_abbreviation_shapes(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": r"""theory T imports Main begin
definition step :: "nat \<Rightarrow> nat \<Rightarrow> nat" where "step a b = a"
abbreviation twice where "twice x \<equiv> step x x"
abbreviation (output) out where "out x \<equiv> step x 0"
abbreviation eq_form where "eq_form x = step 1 x"
lemma "step a b = 0" "step a a = 0" "step a 0 = 0" "step 1 a = 0" "f (step a) = 0"
end
""",
        }
    )
    findings = check_notation(collect([base / "T.thy"]))
    assert [(f.line, f.message) for f in findings] == [
        (6, "step a a is written out; it is the abbreviation twice"),
    ]


def test_included_abbreviations(make_project: MakeProject) -> None:
    # An included session's abbreviation is no part of the project's vocabulary.
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T",
            "T.thy": 'theory T imports "Lib.L" begin\nlemma "step a a = 0" "lib_c x = 0"\nend',
            "lib/ROOT": "session Lib = HOL + theories L",
            "lib/L.thy": "theory L imports Main begin\n"
            'definition step :: "nat \\<Rightarrow> nat \\<Rightarrow> nat" where "step a b = a"\n'
            'abbreviation twice where "twice x \\<equiv> step x x"\n'
            'definition lib_c :: "nat \\<Rightarrow> nat" ("\\<C>") where "lib_c x = x"\nend',
        }
    )
    findings = check_notation(collect([base / "T.thy"], [base / "lib"]))
    assert [(f.line, f.message.split(" is written out")[0]) for f in findings] == [(2, "lib_c")]
