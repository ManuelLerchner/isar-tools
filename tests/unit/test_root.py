from pathlib import Path

import pytest

from isar_tools.project.root import Diagnostic, parse_root, read_root

FULL = """
chapter_definition AFP (main) description "Archive"
chapter_definition Bare
chapter AFP

session "My-Session" (main timing) in "src" = "HOL-Library" +
  description \\<open>A session.\\<close>
  options [timeout = 600, document = pdf]
  sessions "HOL-Algebra" Other
  directories "sub" more
  theories [document = false]
    Pre
  theories
    Main_Thy
    "sub/Deep"
    Global (global)
    "Other.Imported"
  document_theories Doc
  document_files (in "document") "root.tex" "root.bib"
  export_files (in ".") [1] "*:**.ML"
  export_classpath "lib.jar"

session Child = "My-Session" +
  theories Kid(global)
  document_files "b.tex"
  export_files "out"

session Root_Only =
  theories Top
"""


def messages(text: str) -> list[str]:
    return [d.message for d in parse_root(text).diagnostics]


def test_full_session() -> None:
    root = parse_root(FULL)
    assert root.diagnostics == []
    first, child, top = root.sessions
    assert first.name.text == "My-Session"
    assert first.chapter == "AFP"
    assert first.groups == ["main", "timing"]
    assert first.dir is not None
    assert first.dir.text == "src"
    assert first.parent is not None
    assert first.parent.text == "HOL-Library"
    assert first.description == "A session."
    assert first.options == "[timeout = 600, document = pdf]"
    assert [s.text for s in first.sessions] == ["HOL-Algebra", "Other"]
    assert [d.text for d in first.directories] == ["sub", "more"]
    assert [(t.name.text, t.global_, t.options) for t in first.theories] == [
        ("Pre", False, "[document = false]"),
        ("Main_Thy", False, ""),
        ("sub/Deep", False, ""),
        ("Global", True, ""),
        ("Other.Imported", False, ""),
    ]
    assert [t.text for t in first.document_theories] == ["Doc"]
    assert [f.text for f in first.document_files] == ["root.tex", "root.bib"]
    assert [f.text for f in first.export_files] == ["*:**.ML"]
    assert child.parent is not None
    assert child.parent.text == "My-Session"
    assert [(t.name.text, t.global_) for t in child.theories] == [("Kid", True)]
    assert [f.text for f in child.document_files] == ["b.tex"]
    assert [f.text for f in child.export_files] == ["out"]
    assert top.parent is None
    assert top.chapter == "AFP"


def test_default_chapter() -> None:
    assert parse_root("session A = HOL + theories T").sessions[0].chapter == "Unsorted"


def test_positions() -> None:
    root = parse_root("session A = HOL +\n  theories\n    T\n")
    entry = root.sessions[0].theories[0]
    assert root.lines.line(entry.name.start) == 3


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("session A = HOL-Library + theories T", ["parent session HOL-Library must be quoted"]),
        ("session A = HOL + theories Common/Foo", ["theory name Common/Foo must be quoted"]),
        ("session A = HOL + theories", ["expected at least one theory name"]),
        ("session = HOL", ["expected session name"]),
        ("session A HOL", ["expected = after session name"]),
        ("session A (grp = HOL", ["expected ) after session groups"]),
        ("session A = HOL theories T", ["expected + after parent session"]),
        ("session A = HOL + options x", ["expected [ after options"]),
        ("session A = HOL + options [x", ["unterminated ["]),
        ("session A = HOL + theories T (local)", ["expected global"]),
        ("session A = HOL + theories T (global", ["expected ) after global"]),
        ("session A = HOL + sessions", ["expected at least one session name"]),
        ("session A = HOL + bogus", ["unexpected 'bogus' in session A"]),
        ("stray session A = HOL + theories T", ["unexpected 'stray'; expected session or chapter"]),
        ('session A = HOL + description "open', ["expected description", "unterminated"]),
        ("chapter", ["expected chapter name"]),
    ],
)
def test_diagnostics(text: str, expected: list[str]) -> None:
    got = messages(text)
    assert len(got) == len(expected)
    for message, prefix in zip(got, expected, strict=True):
        assert message.startswith(prefix)


def test_recovers_at_next_session() -> None:
    root = parse_root("session A HOL\nsession B = HOL + theories T")
    assert [s.name.text for s in root.sessions] == ["A", "B"]
    assert root.diagnostics == [Diagnostic("expected = after session name", 10)]


def test_read_root(tmp_path: Path) -> None:
    path = tmp_path / "ROOT"
    path.write_text("session A = HOL + theories T\n", encoding="utf-8")
    root = read_root(path)
    assert root.path == path
    assert [s.name.text for s in root.sessions] == ["A"]
