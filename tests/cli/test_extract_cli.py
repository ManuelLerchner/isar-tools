import json
from pathlib import Path

import pytest

from isar_tools.cli import main
from tests.conftest import Golden, MakeProject

PROJECT = {
    "ROOT": "session S = HOL + theories A B",
    "A.thy": """\
theory A imports Main begin
definition succ :: "nat \\<Rightarrow> nat" where
  "succ n = n + 1"

lemma succ_pos: "succ n > 0"
  unfolding succ_def by simp
end
""",
    "B.thy": """\
theory B imports A begin
locale l = fixes x :: nat begin
lemma succ_pos: "succ x > 0"
  by (rule A.succ_pos)
end
end
""",
    "snippets.toml": """\
[snippets.succ]
why = "shown in chapter 2"

[snippets."l.succ_pos"]
""",
}


@pytest.fixture
def project(make_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = make_project(PROJECT)
    monkeypatch.chdir(base)
    return base


EXTRACT = ["project", "extract"]


def test_print(project: Path, capsys: pytest.CaptureFixture[str], golden: Golden) -> None:
    assert main([*EXTRACT, "succ", "A.succ_pos"]) == 0
    golden("extract/print.txt", capsys.readouterr().out)


def test_json(project: Path, capsys: pytest.CaptureFixture[str], golden: Golden) -> None:
    assert main([*EXTRACT, "B.l.succ_pos", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)[0]["qualified"] == "B.l.succ_pos"
    golden("extract/one.json", out)


def test_missing_and_ambiguous(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*EXTRACT, "succ_pos", "nope", "succ"]) == 1
    captured = capsys.readouterr()
    assert captured.err.splitlines() == [
        "isar project extract: succ_pos: ambiguous: A.succ_pos (A.thy:5), B.l.succ_pos (B.thy:3)",
        "isar project extract: nope: no declaration",
    ]
    assert captured.out.startswith("(* A.thy *)\ndefinition succ")


def test_manifest_write_then_check(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = [*EXTRACT, "--manifest", "snippets.toml", "--out", "out"]
    assert main([*manifest, "--check"]) == 1
    assert "2 snippet(s) differ" in capsys.readouterr().err
    assert main([*manifest, "--write"]) == 0
    assert capsys.readouterr().out == "wrote out/l.succ_pos.thy\nwrote out/succ.thy\n"
    assert (project / "out/succ.thy").read_text().startswith("(* A.thy *)\ndefinition succ ::")
    assert main([*manifest, "--check"]) == 0
    assert main([*manifest, "--write"]) == 0
    assert capsys.readouterr().out == ""
    # An edit to a shown declaration is drift.
    text = (project / "A.thy").read_text().replace("n + 1", "Suc n")
    (project / "A.thy").write_text(text)
    assert main([*manifest, "--check", "--color", "never"]) == 1
    out = capsys.readouterr().out
    assert '-  "succ n = n + 1"\n+  "succ n = Suc n"\n' in out


def test_manifest_file_pins(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "pin.toml").write_text('[snippets.succ_pos]\nfile = "B.thy"\n')
    assert main([*EXTRACT, "--manifest", "pin.toml", "--out", "o", "--write"]) == 0
    assert (project / "o/succ_pos.thy").read_text().startswith("(* B.thy *)\n")
    (project / "pin.toml").write_text('[snippets.succ]\nfile = "B.thy"\n[snippets.nope]\n')
    assert main([*EXTRACT, "--manifest", "pin.toml", "--out", "o", "--write"]) == 1
    assert capsys.readouterr().err.splitlines() == [
        "isar project extract: nope: no declaration",
        "isar project extract: succ: no declaration in B.thy",
    ]


def test_statement(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*EXTRACT, "A.succ_pos", "--statement", "--format", "json"]) == 0
    (row,) = json.loads(capsys.readouterr().out)
    assert (row["source"], row["line"], row["end_line"]) == ('lemma succ_pos: "succ n > 0"\n', 5, 5)
    assert main([*EXTRACT, "l", "--statement"]) == 0
    assert capsys.readouterr().out == "(* B.thy *)\nlocale l = fixes x :: nat\n"


def test_instances_by_name(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T",
            "T.thy": "theory T imports Main begin\n"
            "instantiation nat :: c begin\ninstance by simp\nend\n"
            "global_interpretation q: loc 1\n  by simp\n"
            "interpretation loc 2 by simp\nend\n",
        }
    )
    monkeypatch.chdir(base)
    assert main([*EXTRACT, "--statement", "nat::c", "q"]) == 0
    assert capsys.readouterr().out == (
        "(* T.thy *)\ninstantiation nat :: c\n\n(* T.thy *)\nglobal_interpretation q: loc 1\n"
    )
    assert main([*EXTRACT, "T.nat :: c", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["kind"] == "instance"


def test_outside_the_project(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "p/ROOT": "session P = L + theories A",
            "p/A.thy": 'theory A imports L.B begin\nlemma shared: "True" by simp\nend\n',
            "lib/ROOT": "session L = HOL + theories B",
            "lib/B.thy": "theory B imports Main begin\n"
            'lemma shared: "True" by simp\nlemma only_lib: "True" by simp\n'
            "locale ordering_top = fixes top :: 'a\nclass top = fixes top :: 'a\nend\n",
            "home/src/HOL/Orderings.thy": "theory Orderings imports Main begin\n"
            "class bot = fixes bot :: 'a\nbegin\nend\nend\n",
            "m.toml": '[snippets.bot]\nfile = "~~/src/HOL/Orderings.thy"\n[snippets.only_lib]\n',
        }
    )
    monkeypatch.chdir(base)
    monkeypatch.delenv("ISABELLE_HOME", raising=False)
    project = [*EXTRACT, "--project", "p", "-d", "lib"]
    # A -d session counts when the project has no declaration of the name.
    assert main([*project, "only_lib", "shared", "--statement"]) == 0
    assert capsys.readouterr().out == (
        '(* lib/B.thy *)\nlemma only_lib: "True"\n\n(* p/A.thy *)\nlemma shared: "True"\n'
    )
    # A class wins over a parameter of the same name, its own or a locale's.
    assert main([*project, "top", "--statement"]) == 0
    assert capsys.readouterr().out == "(* lib/B.thy *)\nclass top = fixes top :: 'a\n"
    # names lists the project's declarations only.
    assert main([*NAMES, "p", "-d", "lib", "--format", "csv"]) == 0
    assert "only_lib" not in capsys.readouterr().out
    manifest = [*project, "--manifest", "m.toml", "--out", "o", "--write"]
    assert main(manifest) == 0
    captured = capsys.readouterr()
    assert "note: skipped bot: ~~/src/HOL/Orderings.thy needs ISABELLE_HOME" in captured.err
    assert captured.out == "wrote o/only_lib.thy\n"
    monkeypatch.setenv("ISABELLE_HOME", str(base / "home"))
    assert main([*manifest, "--statement"]) == 0
    assert (base / "o/bot.thy").read_text() == (
        "(* ~~/src/HOL/Orderings.thy *)\nclass bot = fixes bot :: 'a\n"
    )
    (base / "m.toml").write_text('[snippets.x]\nname = "gone"\nfile = "~~/src/HOL/X.thy"\n')
    assert main(manifest) == 1
    assert capsys.readouterr().err == (
        "isar project extract: gone: no declaration in ~~/src/HOL/X.thy\n"
    )


def test_manifest_name_and_proof(project: Path) -> None:
    (project / "m.toml").write_text(
        '[snippets.short]\nname = "A.succ_pos"\n'
        '[snippets.long]\nname = "A.succ_pos"\nproof = true\n'
        '[snippets.plain]\nname = "l.succ_pos"\nproof = false\n'
    )
    assert main([*EXTRACT, "--manifest", "m.toml", "--out", "o", "--write", "--statement"]) == 0
    assert (project / "o/short.thy").read_text() == '(* A.thy *)\nlemma succ_pos: "succ n > 0"\n'
    assert (project / "o/long.thy").read_text().endswith("unfolding succ_def by simp\n")
    assert (project / "o/plain.thy").read_text().endswith('"succ x > 0"\n')
    # `proof = false` holds without --statement too.
    assert main([*EXTRACT, "--manifest", "m.toml", "--out", "o", "--check"]) == 1


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "give a NAME or --manifest"),
        (["x", "--write"], "--out, --write, and --check need --manifest"),
        (["--manifest", "snippets.toml", "--write"], "--manifest takes no NAME and needs --out"),
        (["x", "--manifest", "snippets.toml", "--out", "o"], "--manifest takes no NAME"),
        (["--manifest", "snippets.toml", "--out", "o"], "--manifest needs --write or --check"),
        (["--manifest", "absent.toml", "--out", "o", "--check"], "absent.toml"),
        (["--manifest", "bad.toml", "--out", "o", "--check"], "bad.toml"),
        (["--manifest", "list.toml", "--out", "o", "--check"], "[snippets] must be a table"),
        (["x", "--project", "nowhere"], "nowhere: not a directory"),
    ],
)
def test_invalid(
    project: Path, capsys: pytest.CaptureFixture[str], args: list[str], message: str
) -> None:
    (project / "bad.toml").write_text("[snippets\n")
    (project / "list.toml").write_text("snippets = [1]\n")
    assert main([*EXTRACT, *args]) == 2
    assert message in capsys.readouterr().err


NAMES = ["project", "names"]


@pytest.mark.parametrize(
    ("args", "name"),
    [
        ([], "names.txt"),
        (["--format", "json"], "names.json"),
        (["--format", "markdown"], "names.md"),
        (["--kind", "locale", "--kind", "constant"], "kinds.txt"),
    ],
)
def test_names(
    project: Path, capsys: pytest.CaptureFixture[str], golden: Golden, args: list[str], name: str
) -> None:
    assert main([*NAMES, *args]) == 0
    golden(f"extract/{name}", capsys.readouterr().out)


def test_names_markdown_prose(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T",
            "T.thy": "theory T imports Main begin\n"
            'text \\<open>Uses \\<^const>\\<open>f\\<close>, @{term "a | b"},\n'
            "  and \\<open>x \\<le> y\\<close>.\\<close>\n"
            'definition f :: nat where "f = 0"\nend\n',
        }
    )
    monkeypatch.chdir(base)
    assert main([*NAMES, "--format", "markdown"]) == 0
    assert (
        '| `f` | definition | 4 | Uses `f`, `"a \\| b"`, and `x ≤ y`. |' in capsys.readouterr().out
    )


def test_names_by_name(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*NAMES, "--name", "B.l.succ_pos", "--name", "succ", "--format", "csv"]) == 0
    rows = capsys.readouterr().out.splitlines()
    assert [r.split(",")[0] for r in rows] == ["name", "A.succ", "B.l.succ_pos"]
    # A qualifier with the wrong scope does not match, and the hint names the right one.
    assert main([*NAMES, "--name", "B.succ_pos", "--name", "gone"]) == 1
    assert capsys.readouterr().err.splitlines() == [
        "isar project names: B.succ_pos: no declaration; did you mean A.succ_pos, B.l.succ_pos?",
        "isar project names: gone: no declaration",
    ]


def test_names_derived(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*NAMES, "--derived", "--format", "json"]) == 0
    rows = {r["name"]: r["derived_from"] for r in json.loads(capsys.readouterr().out)["names"]}
    assert rows["A.succ_def"] == "A.succ"
    assert rows["A.succ"] == ""
    assert main([*NAMES, "--derived", "--name", "A.succ_def"]) == 0
    assert "from" in capsys.readouterr().out.splitlines()[1]  # the derived_from column
    assert main([*NAMES, "--name", "A.succ_def"]) == 1  # not listed without --derived


def test_names_derived_interpretation(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories L I",
            "L.thy": 'theory L imports Main begin\nlocale l = assumes a: "True"\nend\n',
            "I.thy": "theory I imports L begin\ninterpretation q: l by simp\nend\n",
        }
    )
    monkeypatch.chdir(base)
    assert main([*NAMES, "--derived", "--name", "I.q.a", "--format", "json"]) == 0
    (row,) = json.loads(capsys.readouterr().out)["names"]
    assert (row["command"], row["derived_from"], row["line"]) == ("interpretation", "L.l.a", 2)


def test_names_of_files(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project(
        {
            "p/ROOT": "session P = HOL + theories A B",
            "p/A.thy": 'theory A imports Main begin\nlemma a: "True" by simp\nend\n',
            "p/B.thy": 'theory B imports Main begin\nlocale l = assumes b: "True"\nend\n',
            "p/I.thy": "theory I imports B begin\ninterpretation q: l by simp\nend\n",
            "alone/C.thy": 'theory C imports Main begin\ndefinition c :: nat where "c = 0"\nend\n',
            "alone/notes.txt": "",
        }
    )
    monkeypatch.chdir(base)
    assert main([*NAMES, "p/A.thy", "alone/C.thy", "p/A.thy", "--format", "json"]) == 0
    rows = [(r["name"], r["session"]) for r in json.loads(capsys.readouterr().out)["names"]]
    assert rows == [("A.a", "P"), ("C.c", "")]
    # A file no session lists still has its interpretations' facts.
    assert main([*NAMES, "p/B.thy", "p/I.thy", "--derived", "--name", "I.q.b"]) == 0
    capsys.readouterr()
    assert main([*NAMES, "alone/notes.txt"]) == 2
    assert "notes.txt: not a directory or .thy file" in capsys.readouterr().err


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_instances_view(
    make_project: MakeProject,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    golden: Golden,
    fmt: str,
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories T",
            "T.thy": "theory T imports Main begin\n"
            "instantiation sign :: numeric_domain begin\ninstance by simp\nend\n"
            "global_interpretation sign_tf: mono_ops sign_ops\n  by simp\n"
            "interpretation loc 2 by simp\nend\n",
        }
    )
    monkeypatch.chdir(base)
    assert main(["project", "instances", "--format", fmt]) == 0
    golden(f"extract/instances.{'txt' if fmt == 'text' else fmt}", capsys.readouterr().out)


def test_names_statements(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*NAMES, "--statements", "--derived", "--format", "json"]) == 0
    rows = {r["name"]: r["statement"] for r in json.loads(capsys.readouterr().out)["names"]}
    assert rows["A.succ_pos"] == 'lemma succ_pos: "succ n > 0"\n'
    assert rows["B.l"] == "locale l = fixes x :: nat\n"
    assert rows["A.succ_def"] == ""  # derived
    assert main([*NAMES, "--statements"]) == 2
    assert "--statements needs --format json or csv" in capsys.readouterr().err


def test_names_statements_of_interpretation_facts(
    make_project: MakeProject, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = make_project(
        {
            "ROOT": "session S = HOL + theories L I",
            "L.thy": 'theory L imports Main begin\nlocale l = assumes a: "True"\nend\n',
            "I.thy": "theory I imports L begin\ninterpretation q: l by simp\nend\n",
        }
    )
    monkeypatch.chdir(base)
    assert main([*NAMES, "--derived", "--statements", "--name", "I.q.a", "--format", "csv"]) == 0
    assert capsys.readouterr().out.splitlines()[1].endswith(",")  # no statement


def test_names_anchors(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*NAMES, "--format", "json"]) == 0
    rows = {
        r["name"]: (r["anchor"], r["url"]) for r in json.loads(capsys.readouterr().out)["names"]
    }
    assert rows["A.succ"] == ("A.succ|const", "Unsorted/S/A.html#A.succ%7Cconst")
    assert rows["B.l.succ_pos"] == ("B.l.succ_pos|fact", "Unsorted/S/B.html#B.l.succ_pos%7Cfact")
    assert rows["B.l.x"] == ("", "")  # a locale parameter has no anchor
