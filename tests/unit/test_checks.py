from pathlib import Path

from isar_tools.checks.findings import CODES, DEFAULT_GROUPS, GROUPS, Finding
from isar_tools.checks.project import check_project
from isar_tools.checks.theory import check_proofs, check_symbols, check_syntax
from isar_tools.project.model import Project
from isar_tools.source.theory import parse_theory
from tests.conftest import MakeProject

P = Path("T.thy")


def codes(findings: list[Finding]) -> list[tuple[int, str]]:
    return [(f.line, f.code) for f in findings]


def test_code_registry() -> None:
    assert set(DEFAULT_GROUPS) < set(GROUPS)
    assert {group for group, _ in CODES.values()} == set(GROUPS)


def test_project_checks(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": """\
session A in "a" = HOL +
  directories gone "sub" "other"
  theories T Missing
  document_files "root.tex" "absent.tex"
  document_files (in "$ISABELLE_HOME/lib") "x.sty"
session B in "b" = HOL +
  theories U
session Nowhere in "nowhere" = HOL + theories X
""",
            "a/T.thy": "theory T imports Main begin end",
            "a/sub/T.thy": "theory T imports Main begin end",
            "a/other/Orphan.thy": "theory Orphan imports Main begin end",
            "a/document/root.tex": "",
            "b/U.thy": "theory U imports Main begin end",
        }
    )
    findings = check_project(Project.load(base))
    root = base / "ROOT"
    got = [(f.path, f.line, f.code) for f in findings]
    assert got == [
        (root, 3, "missing-theory"),
        (root, 8, "missing-theory"),
        (root, 2, "missing-directory"),
        (root, 4, "missing-document-file"),
        (root, 1, "duplicate-theory-name"),
        (root, 8, "missing-directory"),
        (base / "a/sub/T.thy", 1, "unreached-theory"),
        (base / "a/other/Orphan.thy", 1, "unreached-theory"),
    ]
    duplicate = next(f for f in findings if f.code == "duplicate-theory-name")
    assert duplicate.message == (
        "two theories T on the search path of session A (T.thy, sub/T.thy); only one is built"
    )


def test_included_sessions_are_not_checked(make_project: MakeProject) -> None:
    base = make_project(
        {
            "own/ROOT": "session Own = Lib + theories O",
            "own/O.thy": 'theory O imports "Lib.L" begin\nlibcmd x\nend',
            "lib/ROOT": "session Lib = HOL + directories gone theories L Missing",
            "lib/L.thy": 'theory L imports Main keywords "libcmd" :: thy_decl begin end',
            "lib/Unused.thy": "theory Unused imports Main begin end",
        }
    )
    project = Project.load(base / "own", [base / "lib", base / "own"])
    assert check_project(project) == []
    assert [s.name for s in project.own_sessions] == ["Own"]
    assert project.theory_files() == [base / "own/O.thy"]
    assert "libcmd" in project.keywords_for(base / "own/O.thy")


def test_duplicate_session_across_include_is_silent(make_project: MakeProject) -> None:
    base = make_project(
        {
            "own/ROOT": "session S = HOL + theories A",
            "own/A.thy": "theory A imports Main begin end",
            "lib/ROOT": "session S = HOL + theories B",
            "lib/B.thy": "theory B imports Main begin end",
        }
    )
    project = Project.load(base / "own", [base / "lib"])
    assert check_project(project) == []


PROOFS = """\
theory T imports Main begin
lemma a: "A" sorry
lemma b: "B" oops
lemma c: "C" \\<proof>
lemma d: "D"
  apply simp
lemma "E"
  apply simp
definition f where "f = 1"
lemma g: "G"
proof -
"""


def test_proof_checks() -> None:
    findings = check_proofs(P, parse_theory(PROOFS))
    assert codes(findings) == [
        (2, "unfinished-proof"),
        (3, "oops"),
        (4, "unfinished-proof"),
        (5, "unclosed-proof"),
        (7, "unclosed-proof"),
        (10, "unclosed-proof"),
    ]
    assert [f.message for f in findings[3:]] == [
        "proof of lemma d not finished before lemma",
        "proof of lemma not finished before definition",
        "proof of lemma g not finished before the end of the file",
    ]


SYNTAX = """\
theory T imports Main begin
section \\<open>Fine\\<close>
text %invisible \\<open>Tagged\\<close>
subsection Word
text
lemma x: "A" by simp
text \\<open>one\\<close> \\<open>two\\<close>
text \\<comment> \\<open>c\\<close> "string"
"""


def test_syntax_checks() -> None:
    findings = check_syntax(P, parse_theory(SYNTAX))
    assert codes(findings) == [(5, "document-argument"), (7, "document-argument")]
    assert findings[0].message.startswith("text expects a text argument")
    assert findings[1].message.startswith("unexpected '\\\\<open>two\\\\<close>' after the text")


def test_lexical_errors() -> None:
    for text, what in [
        ("(* x", "comment"),
        ('"x', "string"),
        ("`x", "alternative string"),
        ("{* x", "verbatim block"),
        ("\\<open>x", "cartouche"),
        ("‹x", "cartouche"),
    ]:
        findings = check_syntax(P, parse_theory("end\n" + text))
        assert [(f.line, f.column, f.message) for f in findings] == [(2, 1, f"unterminated {what}")]


def test_symbol_checks() -> None:
    theory = parse_theory('lemma "A ⟹ B" (* é *)\ntext \\<open>ü\\<close>')
    assert [(f.line, f.column, f.message) for f in check_symbols(P, theory)] == [
        (1, 10, "non-ASCII character '⟹' (U+27F9); write \\<Longrightarrow>"),
        (2, 13, "non-ASCII character 'ü' (U+00FC); it has no Isabelle symbol spelling"),
    ]
    assert len(check_symbols(P, theory, include_comments=True)) == 3
