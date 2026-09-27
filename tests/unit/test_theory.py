from pathlib import Path

import pytest

from isar_tools.source.keywords import BUILTIN_COMMANDS, CommandKind, commands_of_import
from isar_tools.source.lexer import Kind, Token, tokenize
from isar_tools.source.theory import (
    GoalBlock,
    KeywordDecl,
    Name,
    Theory,
    keyword_table,
    parse_header,
    parse_theory,
    read_header,
    significant,
    unquote,
)

K = CommandKind

SOURCE = r"""(* preamble *)
section \<open>Title\<close>
theory Foo
  imports Main "HOL-Library.Multiset" \<open>Bar\<close> (* why *)
  keywords "my_cmd" :: thy_decl and "my_goal" :: thy_goal % "proof"
    and "@step" :: prf_decl and "minor" "second"
    and "load" :: thy_load ("ML") and "alias" :: thy_decl == "x"
    and "odd" :: no_such_kind
  abbrevs "==>" = "\<Longrightarrow>"
begin

text \<open>Prose mentioning lemma.\<close>

lemma foo: "A \<Longrightarrow> A" \<comment> \<open>note\<close>
  by simp

private lemma bar:
  assumes "A"
  shows "A"
proof -
  have h: "A" using assms .
  show ?thesis
    apply (rule h)
    done
qed

my_cmd x
my_goal y @step z sorry

lemma baz: "B"
  oops

lemma open_goal: "C"
  apply auto

definition f where "f = 1"
end
"""


@pytest.fixture(scope="module")
def theory() -> Theory:
    return parse_theory(SOURCE)


def test_header(theory: Theory) -> None:
    header = theory.header
    assert header is not None
    assert header.name == Name("Foo", SOURCE.index("Foo"))
    assert [i.text for i in header.imports] == ["Main", "HOL-Library.Multiset", "Bar"]
    assert [(k.name, k.kind) for k in header.keywords] == [
        ("my_cmd", K.THY_DECL),
        ("my_goal", K.THY_GOAL),
        ("@step", K.PRF_DECL),
        ("minor", None),
        ("second", None),
        ("load", K.THY_LOAD),
        ("alias", K.THY_DECL),
        ("odd", None),
    ]
    assert header.begin == SOURCE.index("begin")


def test_commands(theory: Theory) -> None:
    got = [(c.name, c.kind) for c in theory.commands]
    assert got == [
        ("section", K.DOCUMENT_HEADING),
        ("theory", K.THY_BEGIN),
        ("text", K.DOCUMENT_BODY),
        ("lemma", K.THY_GOAL_STMT),
        ("by", K.QED),
        ("lemma", K.THY_GOAL_STMT),
        ("proof", K.PRF_BLOCK),
        ("have", K.PRF_GOAL),
        ("using", K.PRF_DECL),
        (".", K.QED),
        ("show", K.PRF_GOAL),
        ("apply", K.PRF_SCRIPT),
        ("done", K.QED_SCRIPT),
        ("qed", K.QED_BLOCK),
        ("my_cmd", K.THY_DECL),
        ("my_goal", K.THY_GOAL),
        ("@step", K.PRF_DECL),
        ("sorry", K.QED),
        ("lemma", K.THY_GOAL_STMT),
        ("oops", K.QED_GLOBAL),
        ("lemma", K.THY_GOAL_STMT),
        ("apply", K.PRF_SCRIPT),
        ("definition", K.THY_DEFN),
        ("end", K.THY_END),
    ]


def test_command_text_excludes_trailing_layout(theory: Theory) -> None:
    lemma = theory.commands[3]
    assert theory.command_text(lemma) == (
        'lemma foo: "A \\<Longrightarrow> A" \\<comment> \\<open>note\\<close>'
    )
    private = theory.commands[5]
    assert theory.command_text(private).startswith("private lemma bar:")
    assert theory.end(private) - theory.start(private) == len(theory.command_text(private))
    assert [t.text for t in theory.commands[4].tokens(theory.tokens)] == ["by", " ", "simp"]


def test_goal_blocks(theory: Theory) -> None:
    assert theory.goal_blocks() == [
        GoalBlock(3, 5, True),
        GoalBlock(5, 14, True),
        GoalBlock(15, 18, True),
        GoalBlock(18, 20, True),
        GoalBlock(20, 22, False),
    ]


def test_goal_block_left_open_at_end_of_text() -> None:
    theory = parse_theory('lemma x: "A"\n  apply simp\n')
    assert theory.goal_blocks() == [GoalBlock(0, 2, False)]


def test_document_and_diag_commands_stay_inside_proofs() -> None:
    theory = parse_theory(
        'lemma x: "A"\nproof -\n  txt \\<open>t\\<close>\n  thm refl\n  show ?thesis by simp\nqed\n'
    )
    assert theory.goal_blocks() == [GoalBlock(0, 7, True)]


def test_imports_are_never_commands() -> None:
    theory = parse_theory("theory A imports lemma begin end")
    assert [c.name for c in theory.commands] == ["theory", "end"]


def test_quasi_command_and_trailing_modifier() -> None:
    table = {**BUILTIN_COMMANDS, "where": K.QUASI_COMMAND}
    theory = parse_theory("definition f where x\nprivate\n", table)
    assert [c.name for c in theory.commands] == ["definition", "private"]
    assert theory.commands[1].kind is K.BEFORE_COMMAND


def test_modifier_before_non_command() -> None:
    theory = parse_theory("private foo\n")
    assert [(c.name, c.kind) for c in theory.commands] == [("private", K.BEFORE_COMMAND)]


def test_keyword_with_space() -> None:
    table = {**BUILTIN_COMMANDS, "strictly {": K.PRF_OPEN, "st": K.PRF_ASM}
    theory = parse_theory("strictly {\n  have x by simp\n}\nstrictly other\nst\nstrictly", table)
    assert [c.name for c in theory.commands] == ["strictly {", "have", "by", "}", "st"]


def test_undeclared_symbolic_prefix_is_not_part_of_the_keyword() -> None:
    theory = parse_theory("lemma x: A @proof\n")
    assert [c.name for c in theory.commands] == ["lemma", "proof"]


def test_no_commands() -> None:
    theory = parse_theory("(* only a comment *)\n")
    assert theory.commands == []
    assert theory.header is None


def test_empty_command_text() -> None:
    theory = parse_theory("end")
    empty = type(theory.commands[0])("end", K.THY_END, 0, 0)
    assert theory.command_text(empty) == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("theory", None),
        ("lemma x", None),
        ("theory A", Name("A", 7)),
        ('theory "A" begin', Name("A", 7)),
    ],
)
def test_header_name(text: str, expected: Name | None) -> None:
    header = parse_header(tokenize(text))
    assert (header.name if header else None) == expected


def test_header_without_begin() -> None:
    header = parse_header(tokenize("theory A imports B"))
    assert header is not None
    assert header.begin == -1


def test_header_keyword_tokens_at_end() -> None:
    header = parse_header(tokenize('theory A keywords "k" ::'))
    assert header is not None
    assert header.keywords == (KeywordDecl("k", None, 18),)


def test_unterminated_thy_load_spec() -> None:
    header = parse_header(tokenize('theory A keywords "k" :: thy_load ("ML"'))
    assert header is not None
    assert [k.name for k in header.keywords] == ["k"]


def test_significant_skips_formal_comments() -> None:
    toks = tokenize("a \\<comment> \\<open>c\\<close> b \\<^cancel>x")
    assert [t.text for t in significant(toks)] == ["a", "b", "x"]


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        (Token(Kind.STRING, '"a"', 0), "a"),
        (Token(Kind.CARTOUCHE, "\\<open>a\\<close>", 0), "a"),
        (Token(Kind.CARTOUCHE, "‹a›", 0), "a"),
        (Token(Kind.CARTOUCHE, "\\<open>a›", 0), "\\<open>a›"),
        (Token(Kind.WORD, "a", 0), "a"),
    ],
)
def test_unquote(token: Token, expected: str) -> None:
    assert unquote(token) == expected


def test_read_header(tmp_path: Path) -> None:
    path = tmp_path / "A.thy"
    path.write_text("theory A imports B begin\n", encoding="utf-8")
    header = read_header(path)
    assert header is not None
    assert [i.text for i in header.imports] == ["B"]


def test_keyword_table_merges_headers_and_imports() -> None:
    header = parse_header(tokenize('theory A imports HOLCF keywords "k" :: diag begin'))
    table = keyword_table([None, header])
    assert table["k"] is K.DIAG
    assert table["fixrec"] is K.THY_DECL
    assert table["lemma"] is K.THY_GOAL_STMT
    assert "lemma" not in keyword_table([header], builtin=False)


def test_commands_of_import() -> None:
    assert commands_of_import("HOL-Eisbach.Eisbach") == {"method": K.THY_DECL}
    assert "time_fun" in commands_of_import("HOL-Library.Time_Commands")
    assert commands_of_import("HOL-Library.Multiset") == {}


def test_commands_of_afp_imports() -> None:
    """AFP commands are known without an AFP checkout (generated table)."""
    assert commands_of_import("Deriving.Compare_Order_Instances")["derive"] is K.THY_DECL
    assert commands_of_import("Deriving")["derive"] is K.THY_DECL
    # Old-style path imports name the entry's directory, which is its session.
    assert commands_of_import("$AFP/Deriving/Derive")["derive"] is K.THY_DECL
    assert commands_of_import("../Deriving/Derive")["derive"] is K.THY_DECL
    assert commands_of_import("No_Such_Entry.T") == {}
    theory = parse_theory('theory A imports "Deriving.Derive" begin\nderive linorder t\nend')
    assert [c.name for c in theory.commands] == ["theory", "derive", "end"]


def test_theory_uses_imported_session_commands() -> None:
    theory = parse_theory('theory A imports "HOL-Eisbach.Eisbach" begin\nmethod m = simp\nend')
    assert [c.name for c in theory.commands] == ["theory", "method", "end"]
