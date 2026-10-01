import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import Golden, MakeProject

DEFS = r"""theory Defs imports Main begin
definition sq :: "nat \<Rightarrow> nat" ("\<lfloor>_\<rfloor>\<^sup>2") where "sq n = n * n"
abbreviation twice :: "nat \<Rightarrow> nat" ("2\<times>_" [80] 80) where "twice n \<equiv> n + n"
class widening =
  fixes widen :: "'a \<Rightarrow> 'a \<Rightarrow> 'a" (infixl "\<nabla>" 65)
record spec =
  sk :: nat ("skip\<^sup>#")
locale walk =
  fixes step :: "nat \<Rightarrow> nat \<Rightarrow> bool"
    ("_ \<rightarrow>\<^sub>w/ _" [50, 50] 50)
begin
abbreviation reach :: "nat \<Rightarrow> nat \<Rightarrow> bool"
  ("_ \<rightarrow>\<^sup>*/ _" [50, 50] 50)
  where "reach \<equiv> step\<^sup>*\<^sup>*"
abbreviation (input) flip where "flip x y \<equiv> step y x"
definition dead :: nat ("\<D>") where "dead = 0"
end
locale routed = walk st
  for st :: "nat \<Rightarrow> nat \<Rightarrow> bool" ("\<S>")
end
"""
USES = r"""theory Uses imports Defs begin
context walk begin
abbreviation path ("\<P>") where "\<P> \<equiv> reach"
end
end
"""
MANIFEST = """\
[notation.sq]
args = ["n"]
reads = "the square of n"   # the project's own prose, ignored

[notation.twice]
args = ["n"]

[notation.widen]
args = ["a", "b"]

[notation.sk]
name = "spec.sk"
args = ["S"]

[notation.step]
name = "walk.step"
args = ["x", "y"]

[notation."walk.reach"]
args = ["x", "y"]

[notation."walk.flip"]
args = ["x", "y"]

[notation.st]
name = "routed.st"

[notation.path]
name = "walk.path"
file = "Uses.thy"
"""


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories Defs Uses",
            "Defs.thy": DEFS,
            "Uses.thy": USES,
            "notation.toml": MANIFEST,
        }
    )
    monkeypatch.chdir(base)
    return base


NOTATION = ["project", "notation"]


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, list[str]]:
    status = main([*NOTATION, *args])
    captured = capsys.readouterr()
    return status, captured.out, captured.err.splitlines()


def test_json(project: Path, capsys: pytest.CaptureFixture[str], golden: Golden) -> None:
    status, out, err = run(capsys, "notation.toml")
    assert (status, err) == (0, [])
    rows = {row["key"]: row for row in json.loads(out)["notation"]}
    shown = {key: (r["kind"], r["scope"], r["symbol"], r["printed"]) for key, r in rows.items()}
    assert shown == {
        "path": ("locale_abbreviation", "walk", r"\<P>", True),
        "sk": ("record_field", "global", r"skip\<^sup># S", True),
        "sq": ("constant", "global", r"\<lfloor>n\<rfloor>\<^sup>2", True),
        "st": ("locale_parameter", "routed", r"\<S>", True),
        "step": ("locale_parameter", "walk", r"x \<rightarrow>\<^sub>w y", True),
        "twice": ("constant", "global", r"2\<times>n", True),
        "walk.flip": ("locale_abbreviation", "walk", "flip x y", False),
        "walk.reach": ("locale_abbreviation", "walk", r"x \<rightarrow>\<^sup>* y", True),
        "widen": ("class_parameter", "global", r"a \<nabla> b", True),
    }
    assert rows["sq"]["unicode"] == "⌊n⌋⇧2"
    assert rows["walk.flip"]["expansion"] == {"lhs": "flip x y", "rhs": "step y x"}
    # A locale parameter has no anchor of its own; its locale has.
    assert (rows["step"]["url"], rows["step"]["owner_url"]) == (
        None,
        "Unsorted/S/Defs.html#Defs.walk%7Clocale",
    )
    golden("notation/notation.json", out)


def test_write_then_check(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = ["notation.toml", "--out", "gen/notation.json"]
    assert run(capsys, *out, "--check")[0] == 1
    assert run(capsys, *out, "--write")[1] == "wrote gen/notation.json\n"
    assert run(capsys, *out, "--check") == (0, "", [])
    # A changed mixfix is drift.
    (project / "Defs.thy").write_text(DEFS.replace(r'("skip\<^sup>#")', r'("sk\<^sup>#")'))
    status, diff, err = run(capsys, *out, "--check", "--color", "never")
    assert (status, err) == (1, ["gen/notation.json differs from the theories"])
    assert '-      "symbol": "skip\\\\<^sup># S",\n' in diff
    assert '+      "symbol": "sk\\\\<^sup># S",\n' in diff


def test_unsupported_and_missing(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "bad.toml").write_text(
        '[notation.dead]\nname = "walk.dead"\n'
        '[notation.gone]\nname = "walk.gone"\n[notation.nope]\n'
        "[notation.sq]\n"
        "[notation.walk]\n"
    )
    status, out, err = run(capsys, "bad.toml")
    assert (status, out) == (1, "")
    assert err == [
        "isar project notation: Defs.thy:16: dead: a definition inside walk is not supported",
        "isar project notation: gone: walk.gone: no declaration",
        "isar project notation: nope: no declaration",
        "isar project notation: Defs.thy:2: sq: "
        'fewer arguments than the slots of "\\<lfloor>_\\<rfloor>\\<^sup>2"',
        "isar project notation: Defs.thy:8: walk: a locale is not a constant",
    ]


def test_anchors_in_the_build(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    page = project / "html/Unsorted/S/Defs.html"
    page.parent.mkdir(parents=True)
    page.write_text('<span id="Defs.sq|const"></span><span id="Defs.walk|locale"></span>')
    (project / "few.toml").write_text(
        '[notation.sq]\nargs = ["n"]\n[notation.step]\nname = "walk.step"\nargs = ["x", "y"]\n'
    )
    assert run(capsys, "few.toml", "--browser-info", "html")[0] == 0
    page.write_text('<span id="Defs.walk|locale"></span>')
    status, _, err = run(capsys, "notation.toml", "--browser-info", "html")
    assert status == 1
    assert "isar project notation: Uses.thy:3: path: no page Unsorted/S/Uses.html in html" in err
    assert (
        "isar project notation: Defs.thy:2: sq: Unsorted/S/Defs.html has no anchor Defs.sq|const"
        in err
    )


def test_owners(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories A B C",
            "A.thy": "theory A imports Main begin\nlocale l = fixes x :: nat\nend\n",
            "B.thy": "theory B imports Main begin\nlocale l = fixes y :: nat\nend\n",
            "C.thy": "theory C imports A B begin\n"
            'context l begin\nabbreviation a where "a \\<equiv> 0"\nend\n'
            'context order begin\nabbreviation (output) b where "b \\<equiv> 1"\nend\nend\n',
            "n.toml": '[notation.a]\nname = "l.a"\n[notation.b]\nname = "order.b"\n',
        }
    )
    monkeypatch.chdir(base)
    status, _, err = run(capsys, "n.toml")
    assert (status, err) == (
        1,
        ["isar project notation: C.thy:3: a: l is ambiguous: A.thy:2, B.thy:2"],
    )
    (base / "n.toml").write_text('[notation.b]\nname = "order.b"\n')
    status, out, _ = run(capsys, "n.toml")
    (row,) = json.loads(out)["notation"]
    assert (row["owner"], row["owner_url"], row["mode"], row["printed"]) == (
        "order",
        None,
        "output",
        True,
    )


def test_invalid(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "notation.toml", "--write")[0] == 2
    assert run(capsys, "notation.toml", "--out", "x.json")[0] == 2
    assert run(capsys, "notation.toml", "--browser-info", "notation.toml")[2] == [
        "isar project: notation.toml: not a directory"
    ]
    (project / "bad.toml").write_text('[notation.sq]\nargs = "n"\n')
    assert run(capsys, "bad.toml")[2] == ["isar project: sq: args must be a list of strings"]


def test_anchors_the_sources_cannot_give(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories C",
            "C.thy": "theory C imports Main begin\n"
            'context order begin\nabbreviation b where "b \\<equiv> 1"\nend\nend\n',
            # A theory of no session: its anchor is only in the build.
            "Loose.thy": 'theory Loose imports Main begin\ndefinition c where "c = 0"\nend\n',
            "n.toml": '[notation.b]\nname = "order.b"\n[notation.c]\nfile = "Loose.thy"\n',
            "html/HOL/HOL/Orderings.html": '<i id="Orderings.order|locale"></i>',
            "html/HOL/HOL-Library/Lib.html": '<i id="Lib.order|locale"></i>',
            "html/Unsorted/S/C.html": '<i id="C.order.b|const"></i>',
            "html/Other/Loose/Loose.html": '<i id="Loose.c|const"></i>',
        }
    )
    monkeypatch.chdir(base)
    built = ["n.toml", "--browser-info", "html"]
    status, _, err = run(capsys, *built)
    assert (status, err) == (
        1,
        [
            "isar project notation: C.thy:3: b: order: 2 definitions: "
            "HOL/HOL-Library/Lib.html#Lib.order%7Clocale, "
            "HOL/HOL/Orderings.html#Orderings.order%7Clocale"
        ],
    )
    status, out, _ = run(capsys, *built, "--prefer", "HOL/HOL/")
    assert status == 0
    b, c = json.loads(out)["notation"]
    assert b["owner_url"] == "HOL/HOL/Orderings.html#Orderings.order%7Clocale"
    assert c["url"] == "Other/Loose/Loose.html#Loose.c%7Cconst"
    (base / "html/Other/Loose/Loose.html").unlink()
    (base / "html/HOL/HOL-Library/Lib.html").unlink()
    (base / "html/HOL/HOL/Orderings.html").unlink()
    status, out, err = run(capsys, *built)
    assert (status, err) == (1, ["isar project notation: Loose.thy:2: c: Loose.c|const: no anchor"])
    (base / "n.toml").write_text('[notation.b]\nname = "order.b"\n')
    status, out, _ = run(capsys, *built)
    assert (status, json.loads(out)["notation"][0]["owner_url"]) == (0, None)
