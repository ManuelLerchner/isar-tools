from pathlib import Path

from isar_tools.checks.locales import check_locales, reportable, term_identifiers
from isar_tools.project.hierarchy import declarations, parse_context
from isar_tools.project.workspace import collect
from isar_tools.source.theory import parse_theory
from tests.conftest import MakeProject

ROOT = 'session S = HOL + theories Base T\nsession Lib in "lib" = HOL + theories L\n'
BASE = r"""theory Base imports Main begin
locale base =
  fixes base_op :: "'a \<Rightarrow> 'a" ("\<gamma>\<^sub>b\<^sub>a\<^sub>s\<^sub>e")
locale base = fixes shadowed_elsewhere
class numeric = fixes class_op :: "'a"
definition real_const where "real_const = 0"
end
"""


def names(text: str) -> list[str]:
    return [name for name, _ in term_identifiers(text)]


def found(make_project: MakeProject, body: str, *args: str) -> list[tuple[int, int, str]]:
    files = {
        "ROOT": ROOT,
        "Base.thy": BASE,
        "T.thy": f"theory T imports Base begin\n{body}\nend\n",
    }
    base = make_project(files)
    findings = check_locales(collect([base / "T.thy"]), allow=args)
    return [(f.line, f.column, f.message.split()[0]) for f in findings]


def test_term_identifiers() -> None:
    assert names("f_x (g_y :: my_type) \\<le> h_z") == ["f_x", "g_y", "h_z"]
    assert names("\\<forall>x_1 y_1. P x_1 y_1 z_1") == ["P", "z_1"]
    assert names("\\<And>(a_1, b_1) :: 'a \\<times> 'b. c_1") == ["c_1"]
    assert names("\\<exists>!e_1. e_1") == []
    assert names("\\<forall>x_1\\<in>set_s. x_1") == ["set_s"]
    assert names("THE t_1. t_1 = u_1") == ["u_1"]
    assert names("\\<lambda>l_1.p_1") == []  # `l_1.p_1` lexes as one qualified name
    assert names("{s_1. s_1} \\<union> {f_1 w_1 | w_1. w_1} \\<union> {a_1, b_1}") == [
        "f_1",
        "a_1",
        "b_1",
    ]
    assert names("{a_1} \\<union> {z_1 | ") == ["a_1", "z_1"]  # unclosed: not a binder
    assert names("let v_1 = w_1 in v_1") == ["w_1"]
    assert names("let (p_1, q_1) = (r_1); s_1 = t_1 in p_1 q_1 s_1 u_1") == ["r_1", "t_1", "u_1"]
    assert names("(let a_1 = b_1) c_1 a_1 \\<and> (let d_1 = e_1") == ["b_1", "c_1", "e_1"]
    assert names("{x_1. x_1 \\<in> {y_1}}") == ["y_1"]
    assert names("{g_1 (h_1) | k_1. k_1}") == ["g_1", "h_1"]
    assert names("?x_1 = 'a_1 \\<and> 1 = List.map_x \\<and> x\\<in>y") == ["x", "y"]
    assert names("x :: nat \\<Rightarrow> bool, y") == ["x", "y"]
    assert names("(x :: 'a::order) = y_1") == ["x", "y_1"]
    assert names("\\<forall>x. \\<forall>::") == []


def test_reportable() -> None:
    assert reportable("enter_local")
    assert not reportable("f_x")  # too short
    assert not reportable("enterlocal")  # no underscore
    assert reportable("\\<gamma>\\<^sub>a\\<^sub>b")  # γ_a_b
    assert not reportable("\\<gamma>\\<^sub>S")  # γ_S
    assert not reportable("\\<^bold>ab_c", 5)


def test_declaration_terms_and_contexts() -> None:
    theory = parse_theory(
        'locale l = p "arg_1" x where "y = 1" + q\n'
        '  for f :: "\'a" ("\\<phi>") and g\n'
        '  + fixes h assumes a [simp]: "h = f" (is "?P") and "g"\n'
        '  defines d: "k \\<equiv> h"\n'
        "context l begin end\n"
        'context fixes c assumes "c = c" begin end\n'
        "context begin end\n"
        "lemma x: True by simp\n"
    )
    locale = next(declarations(theory, Path("T.thy")))
    assert [t.text for t in locale.terms] == [
        '"arg_1"',
        "x",
        '"y = 1"',
        '"h = f"',
        '"g"',
        '"k \\<equiv> h"',
    ]
    assert [p.name for p in locale.for_fixes] == ["f", "g"]
    assert [d.name for d in locale.defines] == ["d"]
    contexts = [parse_context(theory, c, Path("T.thy")) for c in theory.commands]
    named, unnamed, empty = [c for c in contexts if c is not None]
    assert (named.parents, named.terms) == (["l"], [])
    assert ([p.name for p in unnamed.fixes], unnamed.parents) == (["c"], [])
    assert (empty.parents, empty.terms) == ([], [])


def test_free_identifier(make_project: MakeProject) -> None:
    body = 'locale l = base + fixes own_op\n  assumes "own_op = enter_local"'
    assert found(make_project, body) == [(3, 21, "enter_local")]
    assert found(make_project, body, "enter_local") == []


def test_cartouche_position(make_project: MakeProject) -> None:
    body = "locale l =\n  assumes \\<open>x \\<le> no_such_const\\<close>"
    assert found(make_project, body) == [(3, 26, "no_such_const")]


def test_parameters_and_inheritance(make_project: MakeProject) -> None:
    body = r"""locale l = base f_arg for f_arg :: "'a"
  + fixes own_op ("own'_sym")
  defines "def_const \<equiv> own_op"
  assumes "base_op (own_op f_arg) = def_const"
      and "\<gamma>\<^sub>b\<^sub>a\<^sub>s\<^sub>e = own_sym"
      and "class_op = real_const \<and> (\<forall>bnd_var. bnd_var = bnd_var)"
locale m = l + missing_parent +
  assumes "own_op = def_const"
locale n = assumes "base_op = base_op"
"""
    # Only n does not extend base: its base_op is free.
    assert found(make_project, body) == [(10, 21, "base_op"), (10, 31, "base_op")]


def test_contexts(make_project: MakeProject) -> None:
    body = r"""context base begin
context fixes ctx_op assumes "ctx_op = base_op" begin
context assumes "ctx_op = base_op" begin end
end
lemma "ctx_op = ctx_op" by simp
end
instantiation nat :: numeric begin
context assumes "stray_name = inst_name" begin end
end
end"""
    assert found(make_project, body) == [(9, 18, "stray_name"), (9, 31, "inst_name")]


def test_included_sessions(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T",
            "T.thy": 'theory T imports "Lib.L" begin\n'
            'locale t = lib + assumes "lib_op = lib_const"\nend',
            "lib/ROOT": "session Lib = HOL + theories L",
            "lib/L.thy": "theory L imports Main begin\n"
            "locale lib = fixes lib_op\nconsts lib_const :: nat\nend",
        }
    )
    assert len(check_locales(collect([base]))) == 1  # lib: not visible
    assert check_locales(collect([base], [base / "lib"])) == []
