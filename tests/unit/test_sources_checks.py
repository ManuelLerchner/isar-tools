from pathlib import Path

import pytest

from isar_tools.checks.findings import Finding
from isar_tools.checks.sources import (
    check_hygiene,
    check_leftovers,
    check_theory_name,
    invalid_utf8,
)
from isar_tools.source.theory import parse_theory


def codes(findings: list[Finding]) -> list[tuple[int, int, str]]:
    return [(f.line, f.column, f.code) for f in findings]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("theory A imports Main begin end", None),
        ("theory %invisible A imports Main begin end", None),
        ('theory "A" imports Main begin end', None),
        ("theory B imports Main begin end", "theory B in file A.thy; Isabelle expects theory A"),
        ("theory S.A imports Main begin end", "theory name S.A is qualified"),
        ("(* no header *)", None),
    ],
)
def test_theory_name(text: str, message: str | None) -> None:
    findings = check_theory_name(Path("A.thy"), parse_theory(text))
    if message is None:
        assert findings == []
    else:
        (finding,) = findings
        assert finding.code == "theory-name"
        assert message in finding.message


def test_invalid_utf8() -> None:
    data = b"theory A\nimports Main\xff begin"
    with pytest.raises(UnicodeDecodeError) as caught:
        data.decode("utf-8")
    finding = invalid_utf8(Path("A.thy"), data, caught.value)
    assert (finding.line, finding.column, finding.code) == (2, 13, "invalid-utf8")
    assert finding.message == "not UTF-8: byte 0xff"


def test_hygiene() -> None:
    text = "theory A\n\timports Main\t\r\nbegin ‮ end\n"
    assert codes(check_hygiene(Path("A.thy"), text)) == [
        (2, 1, "tab"),
        (2, 15, "carriage-return"),
        (3, 7, "bidi-control"),
    ]
    assert "CRLF" in check_hygiene(Path("A.thy"), "a\r\n")[0].message
    assert "carriage return" in check_hygiene(Path("A.thy"), "a\rb")[0].message
    assert check_hygiene(Path("A.thy"), "theory A begin end\n") == []


@pytest.mark.parametrize(
    ("name", "reserved"),
    [("AUX.thy", True), ("com1.thy", True), ("Aux_Lemmas.thy", False), ("a|b.thy", True)],
)
def test_reserved_file_names(name: str, reserved: bool) -> None:
    found = [f.code for f in check_hygiene(Path(name), "")]
    assert found == (["reserved-file-name"] if reserved else [])


def test_leftovers() -> None:
    text = """theory A imports Main begin
lemma x: "True"
  sledgehammer
  nitpick [expect = none]
  quickcheck
  by simp
thm x
ML_val \\<open>1\\<close>
lemma y: "True" try0 by simp
end
"""
    assert codes(check_leftovers(Path("A.thy"), parse_theory(text))) == [
        (3, 3, "proof-search"),
        (5, 3, "counterexample-search"),
        (7, 1, "diagnostic-command"),
        (8, 1, "diagnostic-command"),
        (9, 17, "proof-search"),
    ]
