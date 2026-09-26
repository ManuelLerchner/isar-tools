from isar_tools.source.symbols import (
    TO_ASCII,
    TO_UNICODE,
    NonAscii,
    decode,
    encode,
    find_non_ascii,
    symbol_length,
)


def test_table_is_a_bijection() -> None:
    assert len(TO_UNICODE) == len(TO_ASCII)
    assert all(TO_ASCII[char] == escape for escape, char in TO_UNICODE.items())


def test_decode_and_encode() -> None:
    ascii_ = "A \\<Longrightarrow> \\<lambda>x. x\\<^sub>1 \\<open>t\\<close>"
    unicode = "A ⟹ λx. x⇩1 ‹t›"
    assert decode(ascii_) == unicode
    assert encode(unicode) == ascii_


def test_unknown_symbols_are_kept() -> None:
    assert decode("\\<nonsense>") == "\\<nonsense>"
    assert encode("é") == "é"


def test_symbol_length() -> None:
    assert symbol_length("\\<Longrightarrow>") == 1
    assert symbol_length("x\\<^sub>1 = y") == 7


def test_find_non_ascii() -> None:
    assert list(find_non_ascii("a⟹é")) == [
        NonAscii(1, "⟹", "\\<Longrightarrow>"),
        NonAscii(2, "é", None),
    ]
