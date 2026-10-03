from pathlib import Path

import pytest

from isar_tools.cli import main


@pytest.mark.parametrize("comment", ["(* isar-ignore: inline-declare *)", "(* isar-ignore *)"])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_suppression(tmp_path: Path, comment: str, placement: str) -> None:
    declare = "declare foo_def [simp]"
    line = f"{comment}\n{declare}" if placement == "before" else f"{declare} {comment}"
    text = f'theory T imports Main begin\ndefinition foo where "foo = 0"\n{line}\nend\n'
    path = tmp_path / "T.thy"
    path.write_text(text)
    assert main(["check", "attributes", str(path), "--fix=all"]) == 0
    assert path.read_text() == text


def test_fix_modes_and_repeated_declarations(tmp_path: Path) -> None:
    text = (
        'theory T imports Main begin\ndefinition foo :: nat where "foo = 0"\n'
        "declare foo_def [code_unfold]\ndeclare foo_def [simp]\nend\n"
    )
    path = tmp_path / "T.thy"
    path.write_text(text)
    assert main(["check", "attributes", str(path), "--fix=safe"]) == 1
    assert path.read_text() == text
    assert main(["check", "attributes", str(path), "--fix=all"]) == 0
    expected = (
        "theory T imports Main begin\n"
        'definition foo :: nat where [code_unfold, simp]: "foo = 0"\nend\n'
    )
    assert path.read_text() == expected
    assert main(["check", "attributes", str(path), "--fix=all"]) == 0
    assert path.read_text() == expected


def test_global_ignore_and_custom_attribute(tmp_path: Path) -> None:
    path = tmp_path / "T.thy"
    text = (
        'theory T imports Main begin\ndefinition foo where "foo = 0"\n'
        "declare foo_def [custom_rules]\nend\n"
    )
    path.write_text(text)
    assert main(["check", "attributes", str(path), "--fix=all"]) == 1
    assert path.read_text() == text
    assert main(["check", "attributes", str(path), "--ignore", "inline-declare"]) == 0
