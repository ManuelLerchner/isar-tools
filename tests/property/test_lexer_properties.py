"""Invariants of the lexer on arbitrary input."""

from hypothesis import given
from hypothesis import strategies as st

from isar_tools.source.lexer import Kind, LineIndex, tokenize

# Fragments that exercise every lexical class, including their unbalanced halves.
FRAGMENTS = [
    "(*",
    "*)",
    "{*",
    "*}",
    '"',
    "`",
    "\\",
    "\\<open>",
    "\\<close>",
    "‹",
    "›",
    "\\<comment>",
    "\\<^sub>",
    "\\<alpha>",
    "lemma",
    "foo.bar",
    "?x",
    "'a",
    "..",
    "::",
    ".",
    "==>",
    " ",
    "\n",
    "\r\n",
    "\r",
    "\t",
    "42",
    "λ",
]
sources = st.lists(st.sampled_from(FRAGMENTS) | st.text(max_size=3)).map("".join)


@given(sources)
def test_tokens_reproduce_input(text: str) -> None:
    assert "".join(t.text for t in tokenize(text)) == text


@given(sources)
def test_tokens_are_contiguous_and_nonempty(text: str) -> None:
    pos = 0
    for tok in tokenize(text):
        assert tok.start == pos
        assert tok.text
        pos = tok.end
    assert pos == len(text)


@given(sources)
def test_error_token_only_at_end(text: str) -> None:
    toks = tokenize(text)
    errors = [i for i, t in enumerate(toks) if t.kind is Kind.ERROR]
    assert errors in ([], [len(toks) - 1])


@given(sources)
def test_newline_tokens_advance_the_line_by_one(text: str) -> None:
    lines = LineIndex(text)
    for tok in tokenize(text):
        if tok.kind is Kind.NEWLINE:
            assert lines.line(tok.end) == lines.line(tok.start) + 1
