from pathlib import Path

from isar_tools.checks.docs import check_docs
from isar_tools.source.theory import parse_theory

P = Path("T.thy")


def found(text: str) -> list[tuple[int, str, str]]:
    return [(f.line, f.code, f.message) for f in check_docs(P, parse_theory(text))]


def test_documented_theory_is_clean() -> None:
    text = """\
section \\<open>Before the header\\<close>
theory T imports Main begin
text \\<open>Why this theory exists.\\<close>
subsection \\<open>Locales\\<close>
text %important \\<open>Why these locales.\\<close>
locale l = fixes x :: nat
text {* An old-style text block. *}
class c = fixes y :: 'a
text \\<open>Before the heading.\\<close>
subsection \\<open>Heading\\<close>
lemma "True" by simp
end
"""
    assert found(text) == []


def test_theory_text_may_follow_preamble_and_precede_header() -> None:
    preamble = (
        "theory T imports Main begin\nhide_const N\ncontext begin\ntext \\<open>t\\<close>\nend"
    )
    assert found(preamble) == []
    before = 'text \\<open>t\\<close>\ntheory T imports Main begin\ndefinition x where "x = 1"'
    assert found(before) == []


def test_undocumented_theory() -> None:
    first_declaration = """\
theory T imports Main begin
section \\<open>S\\<close>
(* a comment is not documentation *)
text_raw \\<open>\\clearpage\\<close>
definition x where "x = (1::nat)" \\<comment> \\<open>nor is a formal comment\\<close>
text \\<open>Too late.\\<close>
"""
    assert found(first_declaration)[0] == (
        1,
        "undocumented-theory",
        "theory has no text block before its first declaration",
    )
    headings_only = "theory T imports Main begin\nsection \\<open>S\\<close>\nend"
    assert [code for _, code, _ in found(headings_only)] == [
        "undocumented-theory",
        "undocumented-heading",
    ]
    assert found('definition x where "x = 1"') == []  # no header, no theory check


def test_undocumented_heading() -> None:
    text = """\
theory T imports Main begin
text \\<open>t\\<close>
definition x where "x = (1::nat)"
section   \\<open>Two
  lines\\<close>
(* comment *)
text_raw \\<open>\\clearpage\\<close>
subsection %important "Tagged"
lemma "True" by simp
paragraph
"""
    assert found(text) == [
        (4, "undocumented-heading", "section 'Two lines' has no text block next to it"),
        (8, "undocumented-heading", "subsection 'Tagged' has no text block next to it"),
        (10, "undocumented-heading", "paragraph '' has no text block next to it"),
    ]


def test_heading_before_header_looks_past_it() -> None:
    documented = (
        "section \\<open>S\\<close>\ntheory T imports Main begin\ntext \\<open>t\\<close>\nend"
    )
    assert found(documented) == []
    undocumented = 'chapter \\<open>C\\<close>\ntheory T imports Main begin\nlemma "True" by simp'
    assert [(line, code) for line, code, _ in found(undocumented)] == [
        (2, "undocumented-theory"),
        (1, "undocumented-heading"),
    ]


def test_undocumented_locale_and_class() -> None:
    text = """\
locale first = fixes x :: nat
text \\<open>t\\<close>
locale l = fixes x :: nat
lemma "True" by simp
class c = fixes y :: 'a
text \\<open>Only after the class does not count.\\<close>
lemma "True" by simp
private class d = fixes z :: 'a
"""
    assert found(text) == [
        (1, "undocumented-locale", "locale first is not preceded by a text block"),
        (5, "undocumented-class", "class c is not preceded by a text block"),
        (8, "undocumented-class", "class d is not preceded by a text block"),
    ]
