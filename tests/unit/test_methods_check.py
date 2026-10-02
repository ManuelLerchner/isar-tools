from pathlib import Path

from isar_tools.checks.methods import check_methods
from isar_tools.source.theory import parse_theory

P = Path("T.thy")


def found(body: str) -> list[tuple[int, int, str, str]]:
    theory = parse_theory(f"theory T imports Main begin\n{body}\nend\n")
    return [(f.line, f.column, f.code, f.message) for f in check_methods(P, theory)]


def test_empty_modifier() -> None:
    body = """lemma "P" by (simp add:)
lemma "P" by (auto simp: intro: a)
lemma "P" by (simp add: a | auto dest:)
lemma "P" apply (induct x arbitrary: rule: r.induct) done
lemma "P" by (simp add: a b[symmetric]) (* ok *)
lemma "P" using foo: by simp"""
    assert found(body) == [
        (2, 20, "empty-modifier", "add: lists nothing"),
        (3, 20, "empty-modifier", "simp: lists nothing"),
        (4, 34, "empty-modifier", "dest: lists nothing"),
        (5, 27, "empty-modifier", "arbitrary: lists nothing"),
    ]


def test_duplicate_fact() -> None:
    body = """lemma "P" by (simp add: a b a)
lemma "P" by (simp add: a a[symmetric] a [symmetric])
lemma "P" by (simp add: a intro: a) (auto simp: a)
lemma "P" by (simp add: [[simp_trace]] (b) b)"""
    assert found(body) == [
        (2, 29, "duplicate-fact", "a is listed twice after add:"),
        (3, 40, "duplicate-fact", "a[symmetric] is listed twice after add:"),
    ]
