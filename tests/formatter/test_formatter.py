"""Golden tests: ``input/X.thy`` formats to ``expected/X.thy`` (default options)
and to ``expected-normalize/X.thy`` (``normalize=True``). Every expected file
is a fixed point. ``UPDATE_GOLDEN=1`` rewrites the expected files."""

import os
from pathlib import Path

import pytest

from isar_tools.formatter.formatter import FormatError, Options, format_theory
from isar_tools.source.files import read_source, write_source
from isar_tools.source.lexer import LAYOUT, tokenize
from isar_tools.source.theory import parse_theory

HERE = Path(__file__).parent
INPUTS = sorted((HERE / "input").glob("*.thy"))
MODES = {"expected": Options(), "expected-normalize": Options(normalize=True)}


def fmt(text: str, options: Options | None = None) -> str:
    return format_theory(parse_theory(text), options)


@pytest.mark.parametrize("mode", sorted(MODES))
@pytest.mark.parametrize("source", INPUTS, ids=lambda p: p.stem)
def test_golden(source: Path, mode: str) -> None:
    options = MODES[mode]
    actual = fmt(read_source(source), options)
    expected = HERE / mode / source.name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        expected.parent.mkdir(exist_ok=True)
        write_source(expected, actual)
    assert actual == read_source(expected)
    assert fmt(actual, options) == actual


@pytest.mark.parametrize("source", INPUTS, ids=lambda p: p.stem)
def test_only_layout_changes(source: Path) -> None:
    text = read_source(source)
    for options in MODES.values():
        before = [(t.kind, t.text) for t in tokenize(text) if t.kind not in LAYOUT]
        after = [(t.kind, t.text) for t in tokenize(fmt(text, options)) if t.kind not in LAYOUT]
        assert after == before


def test_crlf_is_kept() -> None:
    out = fmt("lemma x: A\r\nby simp  \r\n")
    assert out == "lemma x: A\r\n  by simp\r\n"


def test_empty_and_blank() -> None:
    assert fmt("") == ""
    assert fmt("\n\n  \n") == ""


def test_final_newline_is_added() -> None:
    assert fmt("end") == "end\n"


def test_options() -> None:
    assert fmt("lemma x: A\nby simp", Options(indent=4)) == "lemma x: A\n    by simp\n"
    text = "end\n\n\n\nend\n"
    assert fmt(text, Options(max_blank_lines=1)) == "end\n\nend\n"


def test_unterminated_text_is_refused() -> None:
    with pytest.raises(FormatError, match="line 2: unterminated"):
        fmt('end\nlemma "open')


def test_malformed_structure_does_not_crash() -> None:
    text = "qed\nnext\n}\nby simp\ndone\nshow x\n"
    assert fmt(fmt(text)) == fmt(text)


def test_qed_closes_its_block_past_an_open_brace() -> None:
    assert fmt("lemma x: A\nproof -\n{\nqed\n") == "lemma x: A\nproof -\n  {\nqed\n"
