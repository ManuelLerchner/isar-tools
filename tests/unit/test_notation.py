from pathlib import Path

import pytest

from isar_tools.project.names import Entity, entities
from isar_tools.project.notation import (
    NotationError,
    Shape,
    display,
    expansion,
    fill,
    shape,
    template,
)
from isar_tools.source.theory import parse_theory

SOURCE = r"""theory T imports Main begin
definition sq :: "nat \<Rightarrow> nat" ("\<lfloor>_\<rfloor>\<^sup>2") where "sq n = n * n"
definition plain :: nat where "plain = 0"
definition all_n :: "(nat \<Rightarrow> bool) \<Rightarrow> bool"
  (binder "\<forall>\<^sub>n" 10) where "all_n P = True"
consts weight :: "'a \<Rightarrow> nat" (structure)
class widening = fixes widen :: "'a \<Rightarrow> 'a \<Rightarrow> 'a" (infixl "\<nabla>" 65)
record spec = sk :: nat ("skip\<^sup>#")
datatype t = Leaf ("\<bottom>")
locale walk = fixes step :: "nat \<Rightarrow> nat \<Rightarrow> bool" (infix "\<rightarrow>" 50)
begin
abbreviation (input) flip where "flip x y \<equiv> step y x"
definition dead :: nat ("\<D>") where "dead = 0"
lemma fact: "True" by simp
end
locale routed = walk st for st :: "nat \<Rightarrow> nat \<Rightarrow> bool" ("\<S>")
end
"""


@pytest.fixture(scope="module")
def found() -> dict[str, Entity]:
    theory = parse_theory(SOURCE)
    return {e.qualified: e for e in entities(theory, "T", Path("T.thy"))}


def test_shapes(found: dict[str, Entity]) -> None:
    assert shape(found["T.sq"]) == Shape("constant", "", "global")
    assert shape(found["T.widening_class.widen"]) == Shape("class_parameter", "widening", "global")
    assert shape(found["T.spec.sk"]) == Shape("record_field", "spec", "global")
    assert shape(found["T.walk.step"]) == Shape("locale_parameter", "walk", "walk")
    assert shape(found["T.routed.st"]) == Shape("locale_parameter", "routed", "routed")
    assert shape(found["T.walk.flip"]) == Shape("locale_abbreviation", "walk", "walk")
    for name, why in (
        ("T.walk.dead", "a definition inside walk"),
        ("T.t.Leaf", "a datatype member of t"),
        ("T.walk.fact", "a fact is not a constant"),
    ):
        with pytest.raises(NotationError, match=why):
            shape(found[name])


def test_templates(found: dict[str, Entity]) -> None:
    assert template(found["T.sq"]) == r"\<lfloor>_\<rfloor>\<^sup>2"
    assert template(found["T.widening_class.widen"]) == r"_ \<nabla> _"
    assert template(found["T.plain"]) == ""
    for name in ("T.all_n", "T.weight"):
        with pytest.raises(NotationError, match="the mixfix"):
            template(found[name])


def test_fill_slots_then_applied_arguments() -> None:
    assert fill(r"\<C>\<^bsub>_,_\<^esub>", "c", ["g", "S", "v"]) == r"\<C>\<^bsub>g,S\<^esub> v"
    # Blocks, breaks, and priorities are layout; a quote escapes the next character.
    assert fill(r"(2_ \<turnstile>/ _ \<rightarrow>//_)", "s", ["G", "c", "d"]) == (
        r"G \<turnstile> c \<rightarrow>d"
    )
    assert fill(r"(\<open>indent=2\<close>'(_'))", "p", ["x"]) == "(x)"
    assert fill("combine'_env\\<^sup>#", "f", ["S"]) == r"combine_env\<^sup># S"
    assert fill("", "carries", ["t", "c"]) == "carries t c"
    # Unterminated text is kept as it stands.
    assert fill(r"(\<open>x _", "p", ["a"]) == "a"
    assert fill(r"\<foo", "p", []) == r"\<foo"


def test_fill_rejects() -> None:
    with pytest.raises(NotationError, match="fewer arguments"):
        fill("_ + _", "plus", ["a"])
    with pytest.raises(NotationError, match="structure index"):
        fill(r"\<one>\<index>", "one", [])


def test_display() -> None:
    assert display(r"\<gamma>\<^sub>D a \<nabla> b") == "γ⇩D a ∇ b"


def test_expansion() -> None:
    assert expansion('abbreviation (input) flip where\n  "flip x  y \\<equiv> step y x"') == (
        "flip x y",
        "step y x",
    )
    assert expansion("abbreviation a where \\<open>a == f\\<close>") == ("a", "f")
    for statement in (
        "abbreviation a",
        'abbreviation a and b where "a \\<equiv> 0" | "b \\<equiv> 1"',
        'abbreviation a where "a = 0"',
        'abbreviation a where "a \\<equiv> (b \\<equiv> c)"',
        'abbreviation a where "a == (b \\<equiv> c)"',
    ):
        with pytest.raises(NotationError):
            expansion(statement)
