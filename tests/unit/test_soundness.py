from pathlib import Path

from isar_tools.checks.soundness import check_soundness
from isar_tools.source.theory import parse_theory

P = Path("T.thy")


def found(body: str) -> list[tuple[int, int, str, str]]:
    theory = parse_theory(f"theory T imports Main begin\n{body}\nend\n")
    return [(f.line, f.column, f.code, f.message) for f in check_soundness(P, theory)]


def test_axiomatization() -> None:
    body = """axiomatization f :: nat where f_ax: "f = 0"
axiomatization g :: nat where "g = 0" and g_pos: "g > 0" "g < 2"
axiomatization h :: nat (* only declares h *)
bnf_axiomatization (setF: 'a) F"""
    assert found(body) == [
        (2, 1, "axiomatization", "axiomatization asserts 1 axiom no proof checks"),
        (3, 1, "axiomatization", "axiomatization asserts 2 axioms no proof checks"),
        (5, 1, "axiomatization", "bnf_axiomatization asserts the BNF laws no proof checks"),
    ]


def test_oracle() -> None:
    assert found("oracle trust = \\<open>K I\\<close>\noracle") == [
        (2, 1, "oracle", "oracle trust makes theorems without a proof"),
        (3, 1, "oracle", "oracle oracle makes theorems without a proof"),
    ]


def test_configurations() -> None:
    body = """declare [[smt_oracle = true, quick_and_dirty]]
lemma "P" using [[smt_oracle]] by smt
declare [[smt_oracle = false, quick_and_dirty=false]]
declare [[smt_oracle =]]
lemma smt_oracle: "True" by simp
text \\<open>@{attributes [[smt_oracle]]}\\<close>"""
    assert found(body) == [
        (2, 11, "smt-oracle", "smt_oracle takes the SMT solver's verdict without a proof"),
        (2, 30, "quick-and-dirty", "quick_and_dirty lets sorry pass in a build"),
        (3, 19, "smt-oracle", "smt_oracle takes the SMT solver's verdict without a proof"),
        (5, 11, "smt-oracle", "smt_oracle takes the SMT solver's verdict without a proof"),
    ]
