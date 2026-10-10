from pathlib import Path

import pytest

from isar_tools.project.names import Entity, entities
from isar_tools.project.notation import (
    NotationError,
    Shape,
    Syntax,
    display,
    expansion,
    fill,
    shape,
    syntax_entries,
    template,
    translation,
    translation_rules,
)
from isar_tools.source.lexer import Token, tokenize
from isar_tools.source.theory import parse_theory, significant

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
    def of(name: str) -> str:
        return template(found[name].mixfix, found[name].notation)

    assert of("T.sq") == r"\<lfloor>_\<rfloor>\<^sup>2"
    assert of("T.widening_class.widen") == r"_ \<nabla> _"
    assert of("T.plain") == ""
    for name in ("T.all_n", "T.weight"):
        with pytest.raises(NotationError, match="the mixfix"):
            of(name)


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


def _args(source: str) -> list[Token]:
    return list(significant(tokenize(source)))[1:]


def test_syntax_entries() -> None:
    entries = syntax_entries(
        _args(
            r"""syntax (latex output) _a :: "nat \<Rightarrow> nat" ("\<alpha> _" [100] 99)
  "_b" :: nat "_c" :: "nat"
  "_d" :: "nat \<Rightarrow> nat \<Rightarrow> nat" (infixl "\<delta>" 60)"""
        )
    )
    assert list(entries) == [
        Syntax("_a", '"\\<alpha> _" [100] 99', "\\<alpha> _", "latex output"),
        Syntax("_d", 'infixl "\\<delta>" 60', "\\<delta>", "latex output"),
    ]


def test_translation_rules() -> None:
    rules = translation_rules(
        _args(r'translations (logic) "a x" == "CONST f x" "b" "c" \<leftharpoondown> (type) "d"')
    )
    assert list(rules) == [("a x", "==", "CONST f x"), ("c", "\\<leftharpoondown>", "d")]


SYNTAX = {
    s.name: s
    for s in [
        Syntax("_pair", '"\\<langle>_,/ _\\<rangle>"', "\\<langle>_,/ _\\<rangle>", ""),
        Syntax("_bot", '"\\<bottom>"', "\\<bottom>", ""),
        Syntax("_all", 'binder "\\<forall>\\<^sub>s" 10', "\\<forall>\\<^sub>s", ""),
        Syntax("_ix", '"_\\<index>"', "_\\<index>", ""),
        Syntax("_plus", 'infixl "\\<oplus>" 65', "\\<oplus>", ""),
    ]
}


@pytest.mark.parametrize(
    ("lhs", "rhs", "written"),
    [
        ("\\<langle>b, a\\<rangle>", "CONST p a b", "\\<langle>B, A\\<rangle>"),
        ("_pair b a", "CONST T.p a b", "\\<langle>B, A\\<rangle>"),
        ("\\<bottom>", "CONST bot", "\\<bottom>"),
        ("b \\<oplus> a", "CONST p a b", "B \\<oplus> A"),
        ("\\<langle>a, a\\<rangle>", "CONST p a b", None),  # not each variable once
        ("_pair a c", "CONST p a b", None),
        ("\\<langle>a, b\\<rangle>", "CONST p a 0", None),  # a pattern, no variable
        ("\\<langle>a, b\\<rangle>", "CONST p a a", None),
        ("\\<langle>a, b\\<rangle>", "p a b", None),  # no CONST
        ("_all x", "CONST all x", None),  # a binder
        ("_ix x", "CONST ix x", None),  # a structure index
        ("", "CONST c", None),
    ],
)
def test_translation(lhs: str, rhs: str, written: str | None) -> None:
    found = translation(lhs, "==", rhs, SYNTAX)
    assert (found.written(["A", "B"][: len(found.parameters)]) if found else None) == written
