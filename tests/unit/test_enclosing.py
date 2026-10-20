from pathlib import Path

from isar_tools.project.enclosing import enclosing
from isar_tools.source.theory import parse_theory

P = Path("T.thy")
TEXT = r"""theory T imports Main begin
definition f :: nat where
  "f = 0"
lemma induct: "P (n::nat)"
proof (induction n)
  case 0
  have zero: "P 0"
  proof -
    {
      fix x
      show ?thesis sorry
    }
  qed
  then show ?case .
next
  case (Suc n)
  show ?case sorry
qed
lemma script: "Q"
  apply simp
  subgoal by auto
  done
lemma abandoned: "R"
proof -
  have "R \<and> R \<and> R \<and> R \<and> R \<and> R \<and> R \<and> R \<and> R"
  oops
lemma unfinished: "S"
proof -
  have "S"
end
"""


def found(line: int) -> list[tuple[str, str, int, int]]:
    theory = parse_theory(TEXT)
    return [
        (s.command, s.text, theory.lines.line(s.start), theory.lines.line(s.end - 1))
        for s in enclosing(theory, P, line)
    ]


def test_outside() -> None:
    assert found(1) == []


def test_declaration() -> None:
    assert found(3) == [("definition", "T.f", 2, 3)]


def test_cases_and_blocks() -> None:
    assert found(11) == [
        ("lemma", "T.induct", 4, 18),
        ("case", "0", 6, 14),
        ("have", "zero", 7, 13),
        ("{", "", 9, 12),
        ("show", "?thesis", 11, 11),
    ]
    assert found(15) == [("lemma", "T.induct", 4, 18)]
    assert found(17) == [
        ("lemma", "T.induct", 4, 18),
        ("case", "(Suc n)", 16, 17),
        ("show", "?case", 17, 17),
    ]


def test_script() -> None:
    assert found(21) == [("lemma", "T.script", 19, 22), ("subgoal", "", 21, 21)]


def test_oops_and_unfinished() -> None:
    statement = TEXT.splitlines()[24].strip().removeprefix("have ")
    long = statement[:57] + "..."
    assert found(25) == [("lemma", "T.abandoned", 23, 26), ("have", long, 25, 26)]
    assert found(29) == [("lemma", "T.unfinished", 27, 29), ("have", '"S"', 29, 29)]
