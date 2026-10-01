import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import MakeProject

PAGES = {
    "html/HOL/HOL/Orderings.html": '<span id="Orderings.order|locale"></span>'
    '<span id="Orderings.order|class"></span><span id="Orderings.class.order|const"></span>'
    '<a id="top"></a>',
    "html/HOL/HOL-Library/Lib.html": '<span id="Lib.order|locale"></span>',
    "html/Unsorted/S/A.html": '<span id="A.l.x_pos|fact"></span><span id="A.l.x_pos|thm"></span>'
    '<span id="A.f\\&lt;^sub&gt;1|const"></span>',
    # The copy a session renders of another session's theory.
    "html/Unsorted/T/S.A.html": '<span id="A.l.x_pos|fact"></span>',
}


@pytest.fixture
def html(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PAGES)
    monkeypatch.chdir(base)
    return base


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, list[str]]:
    status = main(["project", "anchors", "--browser-info", "html", *args])
    captured = capsys.readouterr()
    return status, captured.out, captured.err.splitlines()


def test_every_anchor(html: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "--format", "json")
    assert status == 0
    assert [(r["anchor"], r["url"]) for r in json.loads(out)["anchors"]] == [
        ("Lib.order|locale", "HOL/HOL-Library/Lib.html#Lib.order%7Clocale"),
        ("Orderings.class.order|const", "HOL/HOL/Orderings.html#Orderings.class.order%7Cconst"),
        ("Orderings.order|class", "HOL/HOL/Orderings.html#Orderings.order%7Cclass"),
        ("Orderings.order|locale", "HOL/HOL/Orderings.html#Orderings.order%7Clocale"),
        ("A.f\\<^sub>1|const", "Unsorted/S/A.html#A.f%5C%3C%5Esub%3E1%7Cconst"),
        ("A.l.x_pos|fact", "Unsorted/S/A.html#A.l.x_pos%7Cfact"),
        ("A.l.x_pos|thm", "Unsorted/S/A.html#A.l.x_pos%7Cthm"),
    ]


def test_by_name(html: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "x_pos", "A.x_pos", "l.x_pos|thm", "--format", "csv")
    assert status == 0
    assert out.splitlines()[1:] == [
        "x_pos,fact,A.l.x_pos|fact,Unsorted/S/A.html#A.l.x_pos%7Cfact",
        "A.x_pos,fact,A.l.x_pos|fact,Unsorted/S/A.html#A.l.x_pos%7Cfact",
        "l.x_pos|thm,thm,A.l.x_pos|thm,Unsorted/S/A.html#A.l.x_pos%7Cthm",
    ]
    assert run(capsys, "--kind", "type", "--kind", "thm", "x_pos")[1].endswith(
        "Unsorted/S/A.html#A.l.x_pos%7Cthm\n"
    )


def test_rivals_are_listed_not_picked(html: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err = run(capsys, "order", "order|locale", "nope", "--kind", "type")
    assert (status, "#" in out) == (1, False)
    assert err == [
        "isar project anchors: order: no anchor",
        "isar project anchors: order|locale: 2 definitions: "
        "HOL/HOL-Library/Lib.html#Lib.order%7Clocale, "
        "HOL/HOL/Orderings.html#Orderings.order%7Clocale",
        "isar project anchors: nope: no anchor",
    ]
    status, _, err = run(capsys, "order")
    assert status == 1
    assert err[0].startswith("isar project anchors: order: 3 definitions: ")
    status, out, _ = run(capsys, "order|locale", "--prefer", "Unsorted/", "--prefer", "HOL/HOL/")
    assert (status, out.split()[-1]) == (0, "HOL/HOL/Orderings.html#Orderings.order%7Clocale")


def test_not_a_directory(html: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["project", "anchors", "--browser-info", "missing"]) == 2
    assert capsys.readouterr().err == "isar project: missing: not a directory\n"


def test_scopes(html: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (html / "html/Unsorted/S/W.html").write_text(
        '<i id="W.w.widen_ge|fact"></i><i id="W.w_class.widen_ge|fact"></i>'
        '<i id="W.W.solve|const"></i><i id="W.I_Interp.solve|const"></i>'
        '<i id="W.I_Interp.other|const"></i>'
    )
    status, out, err = run(capsys, "widen_ge", "W.solve", "W.other", "--format", "csv")
    assert (status, err) == (0, [])
    # A class's fact is rendered in its locale and again in `w_class`: one
    # definition. A suffix of an id beats `Theory.name` for a member.
    assert [line.split(",")[2] for line in out.splitlines()[1:]] == [
        "W.w.widen_ge|fact",
        "W.W.solve|const",
        "W.I_Interp.other|const",
    ]
