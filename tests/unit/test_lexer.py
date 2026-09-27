import pytest

from isar_tools.source.lexer import Kind, LineIndex, Token, tokenize


def kinds(text: str) -> list[tuple[Kind, str]]:
    return [(t.kind, t.text) for t in tokenize(text)]


def test_empty() -> None:
    assert tokenize("") == []


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("\n", Kind.NEWLINE),
        ("\r\n", Kind.NEWLINE),
        ("\r", Kind.NEWLINE),
        (" \t\f\v", Kind.SPACE),
        ("(* a (* nested *) comment *)", Kind.COMMENT),
        ("\\<open>a \\<open>b\\<close> c\\<close>", Kind.CARTOUCHE),
        ("‹a ‹b› c›", Kind.CARTOUCHE),
        ("\\<open>mixed›", Kind.CARTOUCHE),
        ('"a \\" b"', Kind.STRING),
        ('"multi\nline"', Kind.STRING),
        ("`fact`", Kind.ALT_STRING),
        ("{* verbatim (* *}", Kind.VERBATIM),
        ("foo", Kind.WORD),
        ("foo.bar.baz", Kind.WORD),
        ("?x", Kind.WORD),
        ("?x.2", Kind.WORD),
        ("?'a", Kind.WORD),
        ("'a", Kind.WORD),
        ("x'", Kind.WORD),
        ("x\\<^sub>1", Kind.WORD),
        ("\\<alpha>\\<beta>", Kind.WORD),
        ("\\<AA>", Kind.WORD),
        ("42", Kind.WORD),
        ("1.5", Kind.WORD),
        ("==>", Kind.SYM_IDENT),
        ("\\<forall>", Kind.SYMBOL),
        ("\\<^cancel>", Kind.SYMBOL),
        ("\\<proof>", Kind.SYMBOL),
        ("⟹", Kind.SYMBOL),
        ("..", Kind.DELIM),
        ("::", Kind.DELIM),
        (".", Kind.DELIM),
        ("(", Kind.DELIM),
        ("\\", Kind.DELIM),
    ],
)
def test_single_token(text: str, kind: Kind) -> None:
    assert kinds(text) == [(kind, text)]


@pytest.mark.parametrize(
    "text",
    ["(* open", "(* (* *)", '"open', '"escape at end\\', "`open", "{* open", "\\<open>x", "‹x"],
)
def test_unterminated_region_is_one_error_token(text: str) -> None:
    assert kinds("a " + text) == [(Kind.WORD, "a"), (Kind.SPACE, " "), (Kind.ERROR, text)]


def test_longident_stops_before_dotdot() -> None:
    assert kinds("foo..") == [(Kind.WORD, "foo"), (Kind.DELIM, "..")]


def test_lambda_is_not_a_letter() -> None:
    assert kinds("\\<lambda>x") == [(Kind.SYMBOL, "\\<lambda>"), (Kind.WORD, "x")]


def test_unquoted_hyphenated_name_is_three_tokens() -> None:
    assert kinds("HOL-Library") == [
        (Kind.WORD, "HOL"),
        (Kind.SYM_IDENT, "-"),
        (Kind.WORD, "Library"),
    ]


def test_offsets_and_end() -> None:
    toks = tokenize("ab  c")
    assert [(t.start, t.end) for t in toks] == [(0, 2), (2, 4), (4, 5)]
    assert toks[0] == Token(Kind.WORD, "ab", 0)


def test_line_index() -> None:
    idx = LineIndex("a\r\nb\rc\nd")
    assert idx.line_count == 4
    assert [idx.line(o) for o in (0, 1, 3, 5, 7)] == [1, 1, 2, 3, 4]
    assert idx.column(0) == 1
    assert idx.column(4) == 2
