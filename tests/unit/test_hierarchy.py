from pathlib import Path

from isar_tools.project.hierarchy import (
    Assumption,
    Located,
    Parameter,
    closure,
    declarations,
    extends,
    resolve,
)
from isar_tools.source.theory import parse_theory

P = Path("T.thy")

SOURCE = r"""
theory T imports Main begin
class numeric = order + lattice +
  fixes gamma :: "'a::{order_bot, order_top} \<Rightarrow> int set" ("\<gamma>")
    and size :: "'a \<Rightarrow> nat"
  assumes gamma_bot[simp]: "\<gamma> \<bottom> = {}"
  assumes "size x \<ge> 0" "True"
    and [intro]: "a \<le> a"
locale ev =
  fixes f g :: "'d \<Rightarrow> 'a::numeric" (infixl "\<oplus>" 65)
    and h (structure)
  constrains f :: "'d \<Rightarrow> 'a"
  defines "k \<equiv> f"
  notes refl
  assumes sound: "P"
locale mono = ev f g + q: other x where "x = 1" + q2?: third
  for f :: "'d::order \<Rightarrow> 'a" +
  assumes mono: "Q"
begin
end
locale bare
locale only_parents = ev + "quoted"
class empty_class
locale = broken
end
"""


def decls():
    return list(declarations(parse_theory(SOURCE), P))


def test_class() -> None:
    numeric = decls()[0]
    assert (numeric.kind, numeric.name, numeric.line) == ("class", "numeric", 3)
    assert numeric.parents == ["order", "lattice"]
    assert numeric.fixes == [
        Parameter(
            "gamma", "'a::{order_bot, order_top} \\<Rightarrow> int set", '"\\<gamma>"', "\\<gamma>"
        ),
        Parameter("size", "'a \\<Rightarrow> nat", "", ""),
    ]
    assert numeric.assumes == [
        Assumption("gamma_bot", ("\\<gamma> \\<bottom> = {}",)),
        Assumption("", ("size x \\<ge> 0", "True")),
        Assumption("", ("a \\<le> a",)),
    ]
    assert numeric.sorts == ["order_bot", "order_top"]


def test_locale_elements() -> None:
    ev = decls()[1]
    assert ev.parents == []
    assert [(p.name, p.type, p.mixfix, p.notation) for p in ev.fixes] == [
        ("f", "'d \\<Rightarrow> 'a::numeric", 'infixl "\\<oplus>" 65', "\\<oplus>"),
        ("g", "'d \\<Rightarrow> 'a::numeric", 'infixl "\\<oplus>" 65', "\\<oplus>"),
        ("h", "", "structure", ""),
    ]
    assert ev.assumes == [Assumption("sound", ("P",))]
    assert ev.sorts == ["numeric"]


def test_locale_expression() -> None:
    mono = decls()[2]
    assert mono.parents == ["ev", "other", "third"]
    assert mono.fixes == []
    assert mono.assumes == [Assumption("mono", ("Q",))]


def test_other_forms() -> None:
    bare, only_parents, empty_class = decls()[3:]
    assert (bare.name, bare.parents, bare.fixes) == ("bare", [], [])
    assert only_parents.parents == ["ev", "quoted"]
    assert empty_class.kind == "class"
    assert len(decls()) == 6  # `locale = broken` declares nothing


def test_extends_and_resolution() -> None:
    by_name: dict[str, list[Located]] = {}
    for d in decls():
        by_name.setdefault(d.name, []).append(Located(d, "S", False))
    other = parse_theory("locale ev = fixes x")
    external = Located(next(declarations(other, Path("Lib.thy"))), "Lib", True)
    by_name["ev"].insert(0, external)
    assert extends(by_name["numeric"][0]) == ["order", "lattice", "order_bot", "order_top"]
    assert extends(by_name["ev"][1]) == []  # a locale's sorts are not parents
    assert resolve(by_name, "T.ev") is by_name["ev"][1]  # the project's own wins
    assert resolve(by_name, "ev", {Path("Lib.thy")}) is external
    assert resolve(by_name, "nothing") is None

    found, missing = closure(by_name, ["mono", "mono"], lambda path: {P})
    assert [f.decl.name for f in found] == ["ev", "mono"]
    assert missing == ["other", "third"]


def test_cycles_terminate() -> None:
    theory = parse_theory("locale a = b + fixes x\nlocale b = a + fixes y")
    index: dict[str, list[Located]] = {}
    for d in declarations(theory, P):
        index.setdefault(d.name, []).append(Located(d, "S", False))
    found, missing = closure(index, ["a"], lambda path: {P})
    assert [f.decl.name for f in found] == ["b", "a"]
    assert missing == []


def test_odd_syntax() -> None:
    text = 'locale odd = fixes f :: "\'a::{s,}" (infixl "x" and g\n  assumes plain_word'
    odd = next(declarations(parse_theory(text), P))
    assert odd.sorts == ["s"]
    assert [p.name for p in odd.fixes] == ["f"]  # the unclosed mixfix swallows the rest
    assert odd.assumes == [Assumption("", ())]
