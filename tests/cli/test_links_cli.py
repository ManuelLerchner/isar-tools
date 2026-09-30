from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import MakeProject

PAGE = (
    '<span class="entity_def" id="A.l.x_pos|fact">x</span>'
    '<span class="entity_def" id="A.f\\&lt;^sub&gt;1|const">f</span>'
)


@pytest.fixture
def site(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories A",
            "A.thy": "theory A imports Main begin\n"
            'locale l = fixes x :: nat begin\nlemma x_pos: "x \\<ge> 0" by simp\n'
            'lemma other: "True" by simp\nend\nlemma other: "True" by simp\nend\n',
            "browser_info/Unsorted/S/A.html": PAGE,
            "site/index.html": '<a href="Unsorted/S/A.html#A.l.x_pos%7Cfact">ok</a>\n'
            "<a href='Unsorted/S/A.html#A.x_pos%7Cfact'>scope</a>\n"
            '<a href="Unsorted/S/B.html">gone</a> <a href="assets/x.css">css</a>\n'
            '<a href="https://example.org/doc/Unsorted/S/A.html#A.f%5C%3C%5Esub%3E1%7Cconst">'
            "sub</a> <a href='mailto:a@b'>mail</a> <a href=\"https://elsewhere.org/\">x</a>\n",
            "notes.md": "See [x](browser_info/Unsorted/S/A.html#A.l.nope%7Cfact) and "
            "<https://example.org/doc/Unsorted/S/A.html#Other.x%7Cfact>, "
            "[dup](browser_info/Unsorted/S/A.html#A.l.other%7Cfact).\n",
        }
    )
    monkeypatch.chdir(base)
    return base


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, list[str]]:
    status = main(["check", "links", *args])
    return status, capsys.readouterr().out.splitlines()


def test_against_the_build(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    built = ["--browser-info", "browser_info", "--link-base", "https://example.org/doc/"]
    status, out = run(capsys, "site/index.html", "notes.md", *built)
    assert status == 1
    assert out == [
        "notes.md:1:9: broken-anchor: browser_info/Unsorted/S/A.html#A.l.nope%7Cfact: "
        "A.html has no anchor A.l.nope|fact",
        "notes.md:1:62: broken-anchor: https://example.org/doc/Unsorted/S/A.html#Other.x%7Cfact: "
        "A.html has no anchor Other.x|fact",
        "notes.md:1:127: broken-anchor: browser_info/Unsorted/S/A.html#A.l.other%7Cfact: "
        "A.html has no anchor A.l.other|fact",
        "site/index.html:2:10: broken-anchor: Unsorted/S/A.html#A.x_pos%7Cfact: "
        "A.html has no anchor A.x_pos|fact",
        "site/index.html:3:10: broken-link: Unsorted/S/B.html: no page Unsorted/S/B.html",
    ]


def test_against_the_sources(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out = run(capsys, "site/index.html", "notes.md")
    assert status == 1
    assert out == [
        "notes.md:1:62: anchor-name: https://example.org/doc/Unsorted/S/A.html#Other.x%7Cfact: "
        "the anchor does not start with A.",
        "site/index.html:2:10: anchor-name: Unsorted/S/A.html#A.x_pos%7Cfact: "
        "A declares it as A.l.x_pos",
    ]
    # A directory argument names the project; only the links group reads a page.
    assert run(capsys, ".", "site/index.html")[0] == 1
    assert main(["check", "site/index.html"]) == 2
    assert "only the links group reads it" in capsys.readouterr().err
