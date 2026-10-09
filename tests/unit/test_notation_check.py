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


def test_abbreviation_fix_needs_every_parameter(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": r"""theory T imports Main begin
definition step :: "nat \<Rightarrow> nat \<Rightarrow> nat" where "step a b = a"
abbreviation both where "both x y \<equiv> step x x"
lemma "step a a = 0" sorry
end
""",
        }
    )
    [finding] = check_notation(collect([base / "T.thy"]))
    assert finding.code == "spelled-out-abbreviation"
    assert finding.fix is None  # y is not in the term, so the rewrite cannot name it


def test_no_notation(make_project: MakeProject) -> None:
    body = r"""lemma "cop x = x" "widen a b = c"
no_notation cop ("\<kappa>") and widen (infixl "\<nabla>" 65)
lemma "cop x = x" "widen a b = c"
notation cop ("\<kappa>")
lemma "cop x = x" """
    assert found(make_project, body) == [(2, "cop"), (2, "widen"), (6, "cop")]


def test_no_notation_needs_the_same_mixfix_and_mode(make_project: MakeProject) -> None:
    body = r"""no_notation cop ("\<delta>")
no_notation (input) widen (infixl "\<nabla>" 65)
no_notation (output) get ("_\<langle>_\<rangle>" [1000, 0] 1000)
lemma "cop x = x" "widen a b = c" "get s x = y"
notation (input) lift ("\<L>")
lemma "lift f x = y"
no_notation (input) lift ("\<L>")
lemma "lift f x = y" """
    assert found(make_project, body) == [
        (5, "cop"),
        (5, "widen"),
        (5, "get"),
        (7, "lift"),
    ]


def test_no_notation_keeps_other_short_forms(make_project: MakeProject) -> None:
    # gamma_int is also overloaded as gamma, which still holds.
    body = r"""notation gamma_int ("\<G>")
lemma "gamma_int i = {i}"
no_notation gamma_int ("\<G>")
lemma "gamma_int i = {i}"
no_adhoc_overloading gamma == gamma_int
lemma "gamma_int i = {i}" "lift gamma_int i = {i}"
no_adhoc_overloading gamma "lift gamma_int"
lemma "lift gamma_int i = {i}" """
    base = make_project(
        {"ROOT": ROOT, "Base.thy": BASE, "T.thy": f"theory T imports Base begin\n{body}\nend\n"}
    )
    findings = check_notation(collect([base / "T.thy"]))
    assert [(f.line, f.message) for f in findings] == [
        (3, r"gamma_int is written out; its notation is \<G>"),
        (5, "gamma_int is written out; it is overloaded as gamma"),
        (7, "lift gamma_int is written out; it is overloaded as gamma"),
    ]


def test_no_notation_scope(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories Base T U V\n",
            "Base.thy": BASE,
            "T.thy": r"""theory T imports Base begin
context begin
no_notation widen (infixl "\<nabla>" 65)
lemma "widen a b = c"
end
lemma "widen a b = c"
bundle no_kappa begin no_notation cop ("\<kappa>") end
lemma "cop x = x" including no_kappa
lemma "cop x = x"
context loc begin
no_notation op ("\<omega>")
end
lemma (in loc) "op x = x"
no_notation cop ("\<kappa>")
end
""",
            "U.thy": 'theory U imports T begin\nlemma "cop x = x"\nend\n',
            "V.thy": 'theory V imports Base begin\nlemma "cop x = x"\nend\n',
        }
    )
    findings = check_notation(collect([base / "T.thy", base / "U.thy", base / "V.thy"]))
    got = [(f.path.name, f.line, f.message.split(" is written out")[0]) for f in findings]
    assert got == [("T.thy", 6, "widen"), ("T.thy", 9, "cop"), ("V.thy", 2, "cop")]


def test_overloaded_class_parameter_in_instantiation(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": r"""theory T imports Main begin
class dom = fixes gamma :: "'a \<Rightarrow> int set" ("\<gamma>")
class sub = dom + fixes size :: "'a \<Rightarrow> nat" ("\<sigma>")
no_notation gamma ("\<gamma>")
consts gamma_S :: "'s \<Rightarrow> 'v set" ("\<gamma>")
adhoc_overloading gamma_S == gamma
definition g :: "nat \<Rightarrow> nat" where "g n = n"
adhoc_overloading gamma_S == g
instantiation bool :: dom begin
definition gamma_bool_def: "gamma (b :: bool) = {}"
instance proof
  show "gamma True = {}" "g n = n" by (simp_all add: gamma_bool_def g_def)
qed
end
instantiation nat :: "{sub, type}" begin
definition "gamma (n :: nat) = {}"
definition "size (n :: nat) = n"
instance ..
end
instantiation prod :: (dom, dom) dom begin
definition "gamma (p :: 'a \<times> 'b) = {}"
instance ..
end
lemma "gamma True = {}" by simp
end
""",
        }
    )
    findings = check_notation(collect([base / "T.thy"]))
    assert [(f.line, f.message.split(" is written out")[0]) for f in findings] == [
        (12, "g"),  # g is no parameter of dom
        (17, "size"),  # notation, unlike overloading, holds in the instantiation
        (24, "gamma"),
    ]


def test_fix_drops_brackets_in_delimited_slots(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T\n",
            "T.thy": r"""theory T imports Main begin
locale ev =
  fixes aval_abs :: "'e \<Rightarrow> 'd \<Rightarrow> 'a" ("\<lbrakk>_\<rbrakk>\<^sup>\<sharp>")
begin
lemma "aval_abs (Plus e1 e2) d = aval_abs (N 0) d" sorry
end
consts pick :: "nat \<Rightarrow> nat \<Rightarrow> nat \<Rightarrow> nat"
notation pick ("(2_ \<langle>_ /'| _\<rangle>)" [0, 0, 10] 100)
lemma "pick (f a) (g b) (h c) = 0" sorry
end
""",
        }
    )
    findings = check_notation(collect([base / "T.thy"]))
    assert [f.fix.edits[0].text for f in findings if f.fix] == [
        r"\<lbrakk>Plus e1 e2\<rbrakk>\<^sup>\<sharp>",
        r"\<lbrakk>N 0\<rbrakk>\<^sup>\<sharp>",
        # The first slot starts the mixfix; the last one has priority 10.
        r"(f a) \<langle>g b | (h c)\<rangle>",
    ]


SYNTAX = r"""theory Syn imports Main begin
definition rsem :: "nat \<Rightarrow> nat \<Rightarrow> nat set" where "rsem r v = {r, v}"
syntax "_rsem" :: "nat \<Rightarrow> nat \<Rightarrow> nat set" ("\<gamma>\<^bsub>_\<^esub>'(_')")
syntax (input) "_low" :: "nat \<Rightarrow> nat" ("\<lfloor>_\<rfloor>")
syntax (output) "_out" :: "nat \<Rightarrow> nat" ("\<lceil>_\<rceil>")
syntax "_pr" :: "nat \<Rightarrow> nat" ("\<pi> _" [100] 99)
end
"""


def test_translations(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories Syn T U\n",
            "Syn.thy": SYNTAX,
            "T.thy": r"""theory T imports Syn begin
definition low :: "nat \<Rightarrow> nat" where "low n = n"
definition out :: "nat \<Rightarrow> nat" where "out n = n"
definition pr :: "nat \<Rightarrow> nat" where "pr n = n"
definition pair :: "nat \<Rightarrow> nat \<Rightarrow> nat" where "pair a b = a"
lemma "rsem r v = {}" sorry
translations
  "\<gamma>\<^bsub>v\<^esub>(r)" == "CONST rsem r v"
  "_low n" => "CONST low n"
  "\<lceil>n\<rceil>" == "CONST out n"
  "\<pi> n" <= "CONST pr n"
  "\<gamma>\<^bsub>a\<^esub>(0)" == "CONST pair 0 a"
  "\<gamma>\<^bsub>a\<^esub>(b)" == "CONST pair a b c"
lemma "rsem (f r) (Suc v) = {}" "low (Suc n) = 0" "out n = 0" "pr n = 0" "pair 0 a = 0"
no_translations "\<gamma>\<^bsub>v\<^esub>(r)" == "CONST rsem r v"
lemma "rsem r v = {}" sorry
end
""",
            "U.thy": r"""theory U imports Syn begin
lemma "rsem r v = {}" sorry
bundle rs begin
translations "\<gamma>\<^bsub>v\<^esub>(r)" \<rightleftharpoons> "CONST rsem r v"
end
lemma "rsem r v = {}" including rs sorry
end
""",
        }
    )
    findings = check_notation(collect([base / "T.thy", base / "U.thy"]))
    assert [(f.path.name, f.line, f.message) for f in findings] == [
        (
            "T.thy",
            14,
            r"rsem is written out; its notation is \<gamma>\<^bsub>v\<^esub>(r) for rsem r v",
        ),
        ("T.thy", 14, r"low is written out; its notation is \<lfloor>n\<rfloor> for low n"),
        (
            "U.thy",
            6,
            r"rsem is written out; its notation is \<gamma>\<^bsub>v\<^esub>(r) for rsem r v "
            "(bundle rs)",
        ),
    ]
    # The rule reorders the arguments; the subscript slot needs no brackets.
    assert [e.text for f in findings if f.fix for e in f.fix.edits][:2] == [
        r"\<gamma>\<^bsub>Suc v\<^esub>(f r)",
        r"\<lfloor>Suc n\<rfloor>",
    ]


def ambiguities(
    make_project: MakeProject, theories: dict[str, tuple[str, str]]
) -> list[tuple[str, int, str]]:
    """The ambiguous-notation findings of ``{name: (imports, body)}``."""
    files = {
        f"{name}.thy": f"theory {name} imports {imports} begin\n{body}\nend\n"
        for name, (imports, body) in theories.items()
    }
    base = make_project({"ROOT": f"session S = HOL + theories {' '.join(theories)}\n", **files})
    findings = check_notation(collect([base / name for name in files]))
    return [(f.path.stem, f.line, f.message) for f in findings if f.code == "ambiguous-notation"]


AMBIGUOUS = "terms using it are ambiguous"


def test_ambiguous_notation(make_project: MakeProject) -> None:
    base = r"""class dom = fixes gamma :: "'a \<Rightarrow> int set" ("\<gamma>")
consts gamma_S :: "'s \<Rightarrow> 'v set" ("\<gamma>")
adhoc_overloading gamma_S == gamma
consts f :: "nat \<Rightarrow> nat" consts h :: "int \<Rightarrow> nat"
consts g :: "'a \<Rightarrow> nat" ("\<G>")
adhoc_overloading g == f h
notation gamma ("\<gamma>")
definition meet :: "nat \<Rightarrow> nat \<Rightarrow> nat" ("_ \<sqinter>\<^sub>m _" [70, 71] 70)
  where "meet a b = a"
notation (input) f ("\<gamma>")
consts gamma_P :: "'s \<Rightarrow> nat" ("\<gamma> _")"""
    theories = {
        "Base": ("Main", base),
        "T": ("Base", r'definition inf_m (infixl "\<sqinter>\<^sub>m" 65) where "inf_m a b = a"'),
        "Other": ("Main", r"""consts gamma_O :: "'s \<Rightarrow> 'v set" ("\<gamma>")"""),
    }
    assert ambiguities(make_project, theories) == [
        ("Base", 3, r"gamma_S has the notation \<gamma> of gamma (Base.thy:2); " + AMBIGUOUS),
        # Notation given again clashes again.
        ("Base", 8, r"gamma has the notation \<gamma> of gamma_S (Base.thy:3); " + AMBIGUOUS),
        (
            "T",
            2,
            r"inf_m has the notation _ \<sqinter>\<^sub>m _ of meet (Base.thy:9); " + AMBIGUOUS,
        ),
    ]


def test_ambiguous_notation_scope(make_project: MakeProject) -> None:
    body = r"""class dom = fixes gamma :: "'a \<Rightarrow> int set" ("\<gamma>")
no_notation gamma ("\<gamma>")
consts gamma_S :: "'s \<Rightarrow> 'v set" ("\<gamma>")
locale l1 = fixes op :: "nat \<Rightarrow> nat" ("\<omega>")
locale l2 = fixes op2 :: "nat \<Rightarrow> nat" ("\<omega>")
locale l3 = l1 op3 for op3 :: "nat \<Rightarrow> nat" ("\<omega>")
context l1 begin
definition twin :: "nat \<Rightarrow> nat" ("\<omega>") where "twin n = n"
end
bundle b begin notation gamma_S ("\<B>") end
consts beta :: "nat \<Rightarrow> nat" ("\<B>")
unbundle b
consts beta2 :: "nat \<Rightarrow> nat" ("\<B>")
definition rsem :: "nat \<Rightarrow> nat \<Rightarrow> nat set" where "rsem r v = {r, v}"
syntax "_rsem" :: "nat \<Rightarrow> nat \<Rightarrow> nat set" ("\<rho>\<^bsub>_\<^esub>'(_')")
translations "\<rho>\<^bsub>v\<^esub>(r)" == "CONST rsem r v"
consts rho :: "nat \<Rightarrow> nat \<Rightarrow> nat set" ("\<rho>\<^bsub>_\<^esub>'(_')")
consts weight :: "nat \<Rightarrow> nat" ("\<W>\<index>")"""
    assert ambiguities(make_project, {"T": ("Main", body)}) == [
        ("T", 9, r"twin has the notation \<omega> of op (T.thy:5); " + AMBIGUOUS),
        ("T", 14, r"beta2 has the notation \<B> of gamma_S (T.thy:11); " + AMBIGUOUS),
        (
            "T",
            18,
            r"rho has the notation \<rho>\<^bsub>_\<^esub>'(_') of rsem (T.thy:17); " + AMBIGUOUS,
        ),
    ]
