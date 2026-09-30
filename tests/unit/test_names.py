from pathlib import Path

import pytest

from isar_tools.project.names import (
    Entity,
    entities,
    interpretations,
    interpreted,
    matches,
    source,
)
from isar_tools.source.theory import parse_theory

SOURCE = r"""theory T imports Main begin

text \<open>
  The successor.
\<close>
definition succ :: "nat \<Rightarrow> nat" where "succ n = n + 1"
definition (in loc) scoped :: nat where "scoped = 0"
definition f_def: "f = (0::nat)"
definition "g = (1::nat)"
fun even and odd :: "nat \<Rightarrow> bool" where
  "even 0 = True"
| "odd 0 = False"
inductive R :: "'a \<Rightarrow> bool" for r and s where "R x"
partial_function (tailrec) loop :: "nat \<Rightarrow> nat" where "loop n = n"
datatype ('a, 'b) pair = Pair 'a 'b and 'c other = Other
datatype (plugins del: size) 'a box = Box 'a
type_synonym (unclosed
type_synonym 'a tuple = "'a \<times> 'a"
record point = x :: nat
axiomatization where ax: "True"
(* lemma commented_out: "True" *)
lemma top: "True" "\<open>lemma inside: True\<close>"
  by simp
lemma "True" by simp
lemma assumes a: "P" shows "P" using a .
lemma notes [simp] = refl shows "True" by simp
private lemma hidden: "True" by simp
lemmas both = top top
lemmas [simp] = top
named_theorems rules "docs"
locale loc =
  fixes n :: nat
begin
lemma in_loc [simp]: "n = n"
proof -
  show ?thesis by simp
qed
context begin
lemma anon: "True" by simp
end
end
context loc begin
theorem ctx: "True" by simp
end
context fixes m :: nat begin
lemma fixed: "m = m" by simp
end
lemma after: "True" by simp
class c = fixes z :: 'a
bundle b begin end
notepad begin
  have "True" by simp
end
end
"""
P = Path("T.thy")


@pytest.fixture(scope="module")
def found() -> dict[str, Entity]:
    theory = parse_theory(SOURCE)
    return {e.qualified: e for e in entities(theory, "T", P)}


def test_names_kinds_and_scopes(found: dict[str, Entity]) -> None:
    assert {q: (e.kind, e.command) for q, e in found.items()} == {
        "T.succ": ("constant", "definition"),
        "T.loc.scoped": ("constant", "definition"),
        "T.even": ("constant", "fun"),
        "T.odd": ("constant", "fun"),
        "T.R": ("constant", "inductive"),
        "T.loop": ("constant", "partial_function"),
        "T.pair": ("type", "datatype"),
        "T.other": ("type", "datatype"),
        "T.box": ("type", "datatype"),
        "T.pair.Pair": ("constant", "datatype"),
        "T.other.Other": ("constant", "datatype"),
        "T.box.Box": ("constant", "datatype"),
        "T.tuple": ("type", "type_synonym"),
        "T.point": ("type", "record"),
        "T.top": ("fact", "lemma"),
        "T.hidden": ("fact", "lemma"),
        "T.both": ("fact", "lemmas"),
        "T.rules": ("fact", "named_theorems"),
        "T.point.x": ("constant", "record"),
        "T.loc": ("locale", "locale"),
        "T.loc.n": ("constant", "fixes"),
        "T.c_class.z": ("constant", "fixes"),
        "T.loc.in_loc": ("fact", "lemma"),
        "T.loc.anon": ("fact", "lemma"),
        "T.loc.ctx": ("fact", "theorem"),
        "T.fixed": ("fact", "lemma"),
        "T.after": ("fact", "lemma"),
        "T.c": ("class", "class"),
        "T.b": ("bundle", "bundle"),
    }


def test_doc_and_lines(found: dict[str, Entity]) -> None:
    assert found["T.succ"].doc == "The successor."
    assert found["T.loc.scoped"].doc == ""
    assert (found["T.loc.in_loc"].line, found["T.loc.in_loc"].end_line) == (34, 37)


def test_source_includes_proof_and_modifier(found: dict[str, Entity]) -> None:
    theory = parse_theory(SOURCE)
    assert source(theory, found["T.loc.in_loc"]) == (
        'lemma in_loc [simp]: "n = n"\nproof -\n  show ?thesis by simp\nqed\n'
    )
    assert source(theory, found["T.hidden"]) == 'private lemma hidden: "True" by simp\n'
    assert source(theory, found["T.even"]).endswith('| "odd 0 = False"\n')


def test_source_statement(found: dict[str, Entity]) -> None:
    theory = parse_theory(SOURCE)
    assert source(theory, found["T.loc.in_loc"], statement=True) == 'lemma in_loc [simp]: "n = n"\n'
    assert source(theory, found["T.loc"], statement=True) == "locale loc =\n  fixes n :: nat\n"
    assert source(theory, found["T.b"], statement=True) == "bundle b\n"
    # Without a proof or `begin`, the statement is the whole source.
    assert source(theory, found["T.succ"], statement=True) == source(theory, found["T.succ"])


def test_source_dedents() -> None:
    theory = parse_theory('theory T imports Main begin\n  lemma x: "A"\n    by simp\nend\n')
    (entity,) = entities(theory, "T", P)
    assert source(theory, entity) == 'lemma x: "A"\n  by simp\n'


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("in_loc", True),
        ("loc.in_loc", True),
        ("T.in_loc", True),
        ("T.loc.in_loc", True),
        ("U.in_loc", False),
        ("other.in_loc", False),
    ],
)
def test_matches(found: dict[str, Entity], name: str, expected: bool) -> None:
    assert matches(found["T.loc.in_loc"], name) is expected
    assert matches(found["T.after"], "loc.after") is False


def test_source_line_endings() -> None:
    text = 'theory T imports Main begin\r\nlemma x: "A"\r\n  by simp\rend\n'
    theory = parse_theory(text)
    (entity,) = entities(theory, "T", P)
    assert source(theory, entity) == 'lemma x: "A"\n  by simp\n'


DERIVED_SOURCE = r"""theory D imports Main begin
definition f :: nat where "f = 0"
fun g :: "nat \<Rightarrow> nat" where "g 0 = 0" | "g (Suc n) = g n"
inductive ev :: "nat \<Rightarrow> bool" where
  zero: "ev 0" | step: "ev n \<Longrightarrow> ev (Suc (Suc n))" | "ev 4"
datatype t = A | B
locale base = fixes b :: nat assumes pos: "b > 0"
locale ext = base + fixes e :: nat assumes big: "e > b" and "e > 0"
lemma (in base) b_nonzero: "b \<noteq> 0" using pos by simp
interpretation one: base 1 by unfold_locales simp
interpretation base 2 by unfold_locales simp
context base begin
interpretation inner: base 3 by unfold_locales simp
end
end
"""


def test_derived_names() -> None:
    theory = parse_theory(DERIVED_SOURCE)
    found = {e.qualified: e for e in entities(theory, "D", P, derived=True)}
    derived = {q: e.derived_from for q, e in found.items() if e.derived_from}
    assert derived["D.f_def"] == "D.f"
    assert {"D.g.simps", "D.g.induct", "D.g.cases", "D.g.elims"} <= set(derived)
    assert {"D.ev.intros", "D.ev.induct", "D.ev.zero", "D.ev.step"} <= set(derived)
    assert {"D.t.induct", "D.t.inject", "D.t.distinct", "D.t.exhaust"} <= set(derived)
    assert {"D.base_def", "D.base.intro"} <= set(derived)
    assert {"D.ext_def", "D.ext.intro", "D.ext_axioms_def", "D.ext_axioms.intro"} <= set(derived)
    assert "D.base_axioms_def" not in derived  # no parents
    assert found["D.base.pos"].kind == "fact"
    assert found["D.base.b"].kind == "constant"
    # Without derived=True only declared names are listed.
    assert not any(e.derived_from for e in entities(theory, "D", P))


def test_inductive_without_where_has_no_rule_names() -> None:
    theory = parse_theory("theory D imports Main begin\ninductive p :: bool\nend")
    names = {e.name for e in entities(theory, "D", P, derived=True)}
    assert names == {"p", "p.intros", "p.cases", "p.induct", "p.simps"}


def test_record_without_equals() -> None:
    theory = parse_theory("theory D imports Main begin\nrecord r\nend")
    assert [e.name for e in entities(theory, "D", P)] == ["r"]


def test_constructors_selectors_and_consts() -> None:
    theory = parse_theory(
        r"""theory D imports Main begin
datatype (plugins del: size) edge = Skip | is_asg: Assign (var: nat) (rhs: "nat list")
  | Call "nat" ("call _" 60)
  and 'a tree = Leaf | Node "'a tree" (val: 'a) "'a tree"
  for map: tmap
datatype broken
datatype odd = Odd | and = Unnamed
codatatype 'a stream = SCons (shd: 'a) (stl: "'a stream")
consts gamma :: "nat \<Rightarrow> nat set" ("\<lbrakk>_\<rbrakk>") delta :: nat
end"""
    )
    found = {e.qualified: (e.kind, e.command) for e in entities(theory, "D", P)}
    assert found == {
        "D.edge": ("type", "datatype"),
        "D.edge.Skip": ("constant", "datatype"),
        "D.edge.is_asg": ("constant", "datatype"),
        "D.edge.Assign": ("constant", "datatype"),
        "D.edge.var": ("constant", "datatype"),
        "D.edge.rhs": ("constant", "datatype"),
        "D.edge.Call": ("constant", "datatype"),
        "D.tree": ("type", "datatype"),
        "D.tree.Leaf": ("constant", "datatype"),
        "D.tree.Node": ("constant", "datatype"),
        "D.tree.val": ("constant", "datatype"),
        "D.broken": ("type", "datatype"),
        "D.odd": ("type", "datatype"),
        "D.odd.Odd": ("constant", "datatype"),
        "D.stream": ("type", "codatatype"),
        "D.stream.SCons": ("constant", "codatatype"),
        "D.stream.shd": ("constant", "codatatype"),
        "D.stream.stl": ("constant", "codatatype"),
        "D.gamma": ("constant", "consts"),
        "D.delta": ("constant", "consts"),
    }


def test_interpretations() -> None:
    theory = parse_theory(DERIVED_SOURCE)
    facts = list(entities(theory, "D", P, derived=True))
    (interp,) = interpretations(theory, "D", P)  # unqualified and nested are skipped
    assert (interp.qualifier, interp.locale, interp.line) == ("one", "base", 10)
    made = {e.qualified: e.derived_from for e in interpreted(facts, interp)}
    assert made == {"D.one.b_nonzero": "D.base.b_nonzero", "D.one.pos": "D.base.pos"}


def test_optional_qualifier() -> None:
    theory = parse_theory("theory D imports Main begin\ninterpretation q?: base 1 by simp\nend")
    assert [i.qualifier for i in interpretations(theory, "D", P)] == ["q"]
