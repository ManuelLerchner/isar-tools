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
lemma "P" by (induct x arbitrary: rule: r.induct)
lemma "P" by (simp add: a b[symmetric]) (* ok *)
lemma "P" using foo: by simp"""
    assert found(body) == [
        (2, 20, "empty-modifier", "add: lists nothing"),
        (3, 20, "empty-modifier", "simp: lists nothing"),
        (4, 34, "empty-modifier", "dest: lists nothing"),
        (5, 24, "empty-modifier", "arbitrary: lists nothing"),
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


def test_single_apply() -> None:
    body = """lemma "P" apply simp done
lemma "P" using a unfolding b apply (rule c) done
lemma "P" apply simp apply auto done
lemma "P" proof - have "Q" apply simp done then show ?thesis by simp qed"""
    assert [(line, code) for line, _, code, _ in found(body)] == [
        (2, "single-apply"),
        (3, "single-apply"),
        (5, "single-apply"),
    ]
