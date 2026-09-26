from isar_tools.source.theory import goal_name, parse_theory
from isar_tools.stats.metrics import (
    LineClass,
    ProofStats,
    classify_lines,
    line_count,
    theory_stats,
)

B, C, D = LineClass.BLANK, LineClass.CODE, LineClass.DOC

SOURCE = """\
theory T imports Main begin

(* a comment
   over two lines *)
text \\<open>Prose
  continues.\\<close>

lemma foo: "A"
  \\<comment> \\<open>why\\<close>
  by simp

lemma [simp]: "B" by (metis refl) (* trailing *)

theorem (in loc) bar [intro]:
  assumes "A"
  shows "A"
proof -
  have "A"
    sorry
  show ?thesis
    using assms by metis
qed

lemma unfinished: "C"
  apply simp
end
"""


def test_line_count() -> None:
    assert line_count("") == 0
    assert line_count("a") == 1
    assert line_count("a\n") == 1
    assert line_count("a\n\nb") == 3


def test_classify_lines() -> None:
    classes = classify_lines(parse_theory(SOURCE))
    assert [classes[i] for i in range(1, 13)] == [C, B, D, D, D, D, B, C, D, C, B, C]
    assert len(classes) == line_count(SOURCE)


def test_goal_names() -> None:
    theory = parse_theory(SOURCE)
    goals = [c for c in theory.commands if c.name in ("lemma", "theorem")]
    assert [goal_name(theory, c) for c in goals] == ["foo", "", "bar", "unfinished"]


def test_goal_name_with_unbalanced_target() -> None:
    theory = parse_theory("lemma (in loc foo: A")
    assert goal_name(theory, theory.commands[0]) == ""


def test_theory_stats() -> None:
    stats = theory_stats(
        parse_theory(SOURCE), max_line_length=40, methods=frozenset({"metis", "smt"})
    )
    assert stats.name == "T"
    assert (stats.lines, stats.code_lines, stats.doc_lines, stats.blank_lines) == (26, 16, 5, 5)
    assert stats.commands["lemma"] == 3
    assert stats.methods == {"metis": 2}
    assert stats.long_lines == [12]
    assert stats.proofs == [
        ProofStats("foo", "lemma", 8, 1, 1, True, ()),
        ProofStats("", "lemma", 12, 1, 0, True, ()),
        ProofStats("bar", "theorem", 14, 3, 6, True, ("sorry",)),
        ProofStats("unfinished", "lemma", 24, 1, 1, False, ()),
    ]
    assert stats.proofs[2].lines == 9


def test_document_commands_do_not_count_methods() -> None:
    stats = theory_stats(parse_theory("text \\<open>metis\\<close>"), methods=frozenset({"metis"}))
    assert stats.methods == {}


def test_nameless_theory() -> None:
    assert theory_stats(parse_theory("")).name == ""
