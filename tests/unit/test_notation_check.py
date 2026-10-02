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
