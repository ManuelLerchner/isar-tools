"""``soundness`` group: what a theory trusts without a proof.

A theory that builds can still prove ``False``: an axiom, an oracle, or a
configuration that trusts an external answer passes the kernel without
being checked.

- ``axiomatization``: ``axiomatization ... where`` and ``bnf_axiomatization``
  assert their statements. An ``axiomatization`` without ``where`` only
  declares constants and passes;
- ``oracle``: an oracle makes theorems from whatever its ML code returns;
- ``smt-oracle``: ``[[smt_oracle]]`` takes the SMT solver's verdict instead
  of reconstructing its proof;
- ``quick-and-dirty``: ``[[quick_and_dirty]]`` lets ``sorry`` pass in a build.

A configuration set to ``false`` passes. A theory that sets up a new logic
axiomatizes on purpose: keep its axioms with ``(* isar-ignore: axiomatization *)``.
"""

from collections.abc import Iterator
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.source.lexer import Kind, Token
from isar_tools.source.theory import Theory, significant

# configuration -> (code, message)
_TRUSTING = {
    "smt_oracle": ("smt-oracle", "smt_oracle takes the SMT solver's verdict without a proof"),
    "quick_and_dirty": ("quick-and-dirty", "quick_and_dirty lets sorry pass in a build"),
}


def _axioms(toks: list[Token]) -> int:
    """How many statements ``axiomatization ... where`` asserts: the
    ``and``-separated entries after ``where``; 0 without ``where``."""
    where = next((i for i, t in enumerate(toks) if t.text == "where"), -1)
    if where < 0:
        return 0
    return 1 + sum(t.text == "and" for t in toks[where + 1 :])


def _configurations(toks: list[Token]) -> Iterator[Token]:
    """The trusting configurations an attribute list ``[[...]]`` turns on."""
    for i, tok in enumerate(toks):
        if tok.kind is not Kind.WORD or tok.text not in _TRUSTING:
            continue
        if i == 0 or toks[i - 1].text not in ("[", ","):
            continue
        value = toks[i + 2].text if i + 2 < len(toks) and toks[i + 1].text == "=" else "true"
        if value != "false":
            yield tok


def check_soundness(path: Path, theory: Theory) -> list[Finding]:
    findings: list[Finding] = []
    for command in theory.commands:
        toks = list(significant(command.tokens(theory.tokens)))
        start = theory.start(command)
        if command.name == "axiomatization" and (n := _axioms(toks)):
            message = (
                f"axiomatization asserts {n} {'axiom' if n == 1 else 'axioms'} no proof checks"
            )
            findings.append(Finding.at(path, theory.lines, start, "axiomatization", message))
        elif command.name == "bnf_axiomatization":
            message = "bnf_axiomatization asserts the BNF laws no proof checks"
            findings.append(Finding.at(path, theory.lines, start, "axiomatization", message))
        elif command.name == "oracle":
            name = toks[1].text if len(toks) > 1 else "oracle"
            message = f"oracle {name} makes theorems without a proof"
            findings.append(Finding.at(path, theory.lines, start, "oracle", message))
        for tok in _configurations(toks):
            code, message = _TRUSTING[tok.text]
            findings.append(Finding.at(path, theory.lines, tok.start, code, message))
    return findings
