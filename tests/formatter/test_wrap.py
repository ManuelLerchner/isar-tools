from isar_tools.formatter.formatter import Options
from isar_tools.formatter.wrap import format_source


def wrap(text: str, limit: int, **kwargs: int | bool) -> str:
    out = format_source(text, None, Options(max_line_length=limit, **kwargs))  # type: ignore[arg-type]
    assert format_source(out, None, Options(max_line_length=limit, **kwargs)) == out  # type: ignore[arg-type]
    return out


def test_off_by_default() -> None:
    long = 'lemma x: "' + "a " * 80 + '" by simp\n'
    assert format_source(long) == long


def test_one_command_per_line_first() -> None:
    text = (
        'lemma x: "A"\nproof -\n'
        '  have "long_statement_here" using fact_one by (simp add: a b)\nqed\n'
    )
    assert wrap(text, 40) == (
        'lemma x: "A"\nproof -\n  have "long_statement_here"\n'
        "    using fact_one by (simp add: a b)\nqed\n"
    )


def test_shallowest_depth_rightmost_fit() -> None:
    text = "lemma x: A\n  by (simp add: first_fact second_fact (third fourth) fifth_fact)\n"
    assert wrap(text, 40) == (
        "lemma x: A\n  by (simp add: first_fact second_fact\n    (third fourth) fifth_fact)\n"
    )


def test_unbreakable_line_is_kept() -> None:
    text = 'lemma x:\n  "' + "a" * 60 + '"\n'
    assert wrap(text, 20) == text


def test_never_breaks_after_the_keyword() -> None:
    text = 'have "' + "a" * 30 + '"\n'
    assert wrap(text, 10) == text


def test_symbols_count_once() -> None:
    text = 'lemma x: "' + "\\<Longrightarrow> " * 5 + '" by simp\n'
    assert wrap(text, 30) == text


def test_long_first_part_still_breaks_leftmost() -> None:
    text = "lemma x: A\n  by (auto simp: " + "f" * 30 + " " + "g" * 30 + ")\n"
    out = wrap(text, 20)
    assert out == "lemma x: A\n  by (auto simp:\n    " + "f" * 30 + "\n      " + "g" * 30 + ")\n"


def test_frozen_lines_are_not_wrapped() -> None:
    text = 'lemma x: "a\n  b" by (simp add: some long facts here)\n'
    assert wrap(text, 20) == text


def test_crlf_breaks() -> None:
    text = 'lemma x: "A"\r\n  using a_fact by simp\r\n'
    assert wrap(text, 16) == 'lemma x: "A"\r\n  using a_fact\r\n  by simp\r\n'
