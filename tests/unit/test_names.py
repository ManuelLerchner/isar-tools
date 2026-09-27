from pathlib import Path

import pytest

from isar_tools.project.names import Entity, entities, matches, source
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
        "T.tuple": ("type", "type_synonym"),
        "T.point": ("type", "record"),
        "T.top": ("fact", "lemma"),
        "T.hidden": ("fact", "lemma"),
        "T.both": ("fact", "lemmas"),
        "T.rules": ("fact", "named_theorems"),
        "T.loc": ("locale", "locale"),
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
