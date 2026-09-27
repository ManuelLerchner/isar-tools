"""Formatter invariants on generated theory-like text."""

from hypothesis import given, settings
from hypothesis import strategies as st

from isar_tools.formatter.formatter import FormatError, Options
from isar_tools.formatter.wrap import format_source
from isar_tools.source.lexer import LAYOUT, tokenize

WORDS = [
    "theory T imports Main begin",
    "end",
    "lemma x:",
    "theorem",
    'lemma "A"',
    "assumes",
    "shows",
    "and",
    "fixes",
    "for",
    "if",
    "where",
    "begin",
    "context",
    "notepad",
    "instantiation",
    "definition",
    "proof -",
    "proof (cases x)",
    "qed",
    "next",
    "case A",
    "have",
    "show ?thesis",
    "then",
    "using assms",
    "unfolding foo_def",
    "by simp",
    "by (auto simp: a",
    "apply simp",
    "apply (rule conjI)",
    "done",
    "subgoal",
    "sorry",
    "oops",
    ".",
    "..",
    "{",
    "}",
    "(",
    ")",
    "[",
    "]",
    "private",
    "text \\<open>prose\\<close>",
    "\\<comment> \\<open>c\\<close>",
    "(* comment *)",
    "(* multi\n   line *)",
    '"A \\<Longrightarrow>\n   B"',
    '"x"',
    "foo",
]
LAYOUT_BITS = [" ", "  ", "\t", "\n", "\n\n\n", "\r\n", "\n    ", "   \n"]
sources = st.lists(st.sampled_from(WORDS) | st.sampled_from(LAYOUT_BITS), max_size=60).map("".join)
options = st.builds(
    Options,
    indent=st.integers(min_value=1, max_value=4),
    max_blank_lines=st.integers(min_value=0, max_value=3),
    normalize=st.booleans(),
    max_line_length=st.none() | st.integers(min_value=1, max_value=60),
)


def significant(text: str) -> list[tuple[object, str]]:
    return [(t.kind, t.text) for t in tokenize(text) if t.kind not in LAYOUT]


@settings(max_examples=300)
@given(sources, options)
def test_idempotent_and_layout_only(text: str, opts: Options) -> None:
    try:
        once = format_source(text, None, opts)
    except FormatError:
        return
    assert significant(once) == significant(text)
    assert format_source(once, None, opts) == once


@given(sources)
def test_no_trailing_whitespace(text: str) -> None:
    try:
        out = format_source(text)
    except FormatError:
        return
    for line in out.splitlines():
        if line and not line.strip().startswith(("(*", '"')):
            assert line == line.rstrip() or "\n" in text
