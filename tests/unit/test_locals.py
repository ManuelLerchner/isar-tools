from pathlib import Path

from isar_tools.checks.locals import check_unused_locals
from isar_tools.source.theory import parse_theory

P = Path("T.thy")


def found(body: str, *allow: str) -> list[tuple[int, str]]:
    theory = parse_theory(f"theory T imports Main begin\n{body}\nend\n")
    return [(f.line, f.message) for f in check_unused_locals(P, theory, frozenset(allow))]


def test_have_and_its_proof() -> None:
    body = """lemma "P"
proof -
  have used: "A" by simp
  have unused: "B" and also_used [simp]: "C"
  proof -
    show "B" using used by simp
    show "C" by simp
  qed
  show ?thesis using also_used 1 by simp
qed"""
    assert found(body) == [(5, "have unused is cited nowhere in its proof")]


def test_kinds() -> None:
    body = """lemma "P"
proof -
  assume a: "A" and b: "B"
  define x where x_def: "x = (1::nat)"
  note n = refl[where x = 1 and y = 2]
  obtain y where y: "y = x" and z: "True" by simp
  have 1: "R" by simp
  hence h: "Q" by simp
  show s: ?thesis using a 1 by simp
qed"""
    assert found(body) == [
        (4, "assume b is cited nowhere in its proof"),
        (5, "define x_def is cited nowhere in its proof"),
        (6, "note n is cited nowhere in its proof"),
        (7, "obtain y is cited nowhere in its proof"),
        (7, "obtain z is cited nowhere in its proof"),
        (9, "hence h is cited nowhere in its proof"),
    ]
    assert len(found(body, "b", "x_def", "n", "y", "z", "h")) == 0


def test_chained() -> None:
    body = """lemma "P"
proof -
  have a: "A" by simp
  then have b: "B" by simp
  moreover have c: "C" by simp
  ultimately have d: "D" by simp
  from this show ?thesis by simp
qed"""
    assert found(body) == []


def test_contexts() -> None:
    body = """lemma "P"
proof (cases x)
  case A
  have h: "A" by simp
  then show ?thesis by simp
next
  case B
  have h: "B" by simp
  have h: "C" by simp
  { have k: "D" by simp }
  show ?thesis using h k by simp
qed"""
    assert found(body) == [
        (9, "have h is cited nowhere in its proof"),
        (11, "have k is cited nowhere in its proof"),
    ]


def test_rebound_by_its_own_proof() -> None:
    body = """lemma "P"
proof -
  have h: "A" by simp
  have h: "B" using h by simp
  note n = refl
  note n = n[symmetric]
  show ?thesis using h n by simp
qed"""
    assert found(body) == []


def test_have_with_premises() -> None:
    body = """lemma "P"
proof -
  have r: "Q x" if p: "R x" for x using p by simp
  show ?thesis using r by simp
qed"""
    assert found(body) == []


def test_oops_and_unfinished() -> None:
    body = """lemma "P"
proof -
  have a: "A" sorry
  oops
lemma "Q"
proof -
  have b: "B"
  proof -
    have c: "C" """
    # The goals of an unfinished proof bind nothing: unclosed-proof reports it.
    assert found(body) == [(4, "have a is cited nowhere in its proof")]


def test_last_command_chains_nothing() -> None:
    theory = parse_theory('theory T imports Main begin\nlemma "P"\nproof -\n  note a = refl')
    findings = check_unused_locals(P, theory, frozenset())
    assert [(f.line, f.message) for f in findings] == [(4, "note a is cited nowhere in its proof")]
