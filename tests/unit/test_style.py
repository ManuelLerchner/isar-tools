import io

import pytest

from isar_tools.style import Style, write_diff


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_explicit_choices() -> None:
    assert Style.for_stream("always", io.StringIO()).enabled
    assert not Style.for_stream("never", Tty()).enabled


def test_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert Style.for_stream("auto", Tty()).enabled
    assert not Style.for_stream("auto", io.StringIO()).enabled
    monkeypatch.setenv("TERM", "dumb")
    assert not Style.for_stream("auto", Tty()).enabled
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("NO_COLOR", "1")
    assert not Style.for_stream("auto", Tty()).enabled


def test_paint() -> None:
    assert Style(True)("x", "bold", "red") == "\x1b[1;31mx\x1b[0m"
    assert Style(True)("x") == "x"
    assert Style(False)("x", "bold") == "x"


def test_write_diff_keeps_line_endings() -> None:
    out = io.StringIO()
    write_diff("a\r\nb\r\n", "a\r\nc\r\n", "T.thy", out, Style(True))
    assert out.getvalue() == (
        "\x1b[1m--- a/T.thy\x1b[0m\n\x1b[1m+++ b/T.thy\x1b[0m\n"
        "\x1b[36m@@ -1,2 +1,2 @@\x1b[0m\n a\r\n\x1b[31m-b\x1b[0m\r\n\x1b[32m+c\x1b[0m\r\n"
    )
    plain = io.StringIO()
    write_diff("a\n", "b\n", "T.thy", plain, Style(False))
    assert plain.getvalue() == "--- a/T.thy\n+++ b/T.thy\n@@ -1 +1 @@\n-a\n+b\n"
