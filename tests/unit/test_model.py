from pathlib import Path

import pytest

from isar_tools.project.model import Problem, Project, discover_roots, split_qualified
from isar_tools.source.keywords import CommandKind
from tests.conftest import MakeProject

PROJECT = {
    "ROOTS": "Base\n# a comment\nApp  # trailing\n\n",
    "Base/ROOT": """
session Base = HOL +
  directories sub
  theories
    B1
    "sub/B2"
    Sub3
""",
    "Base/B1.thy": 'theory B1 imports Main keywords "mycmd" :: thy_decl begin end',
    "Base/sub/B2.thy": "theory B2 imports B1 begin end",
    "Base/sub/Sub3.thy": 'theory Sub3 imports "B2" Helper "~~/src/HOL/Foo" begin end',
    "Base/sub/Helper.thy": "theory Helper imports Main begin end",
    "Base/Orphan.thy": "theory Orphan imports Main begin end",
    "App/ROOT": """
session "App-Main" in src = Base +
  theories
    A1
    "Base.B1"
""",
    "App/src/A1.thy": 'theory A1 imports "Base.B2" "../Extra" "HOL-Library.Multiset" begin end',
    "App/Extra.thy": "theory Extra imports A1 begin end",
    "App/Nested/ROOT": "session Nested = HOL + theories N",
    "App/Nested/N.thy": "theory N imports Main begin end",
}


@pytest.fixture
def project(make_project: MakeProject) -> Project:
    return Project.load(make_project(PROJECT))


def test_discover_follows_roots(make_project: MakeProject) -> None:
    base = make_project(PROJECT)
    assert discover_roots(base) == [base / "Base/ROOT", base / "App/ROOT"]


def test_discover_without_roots_searches(make_project: MakeProject) -> None:
    base = make_project({"a/ROOT": "", "b/c/ROOT": "", ".git/ROOT": "", "ROOTx": ""})
    assert discover_roots(base) == [base / "a/ROOT", base / "b/c/ROOT"]


def test_discover_tolerates_cycles(make_project: MakeProject) -> None:
    base = make_project({"ROOTS": "a\n", "a/ROOTS": "..\n", "a/ROOT": ""})
    assert discover_roots(base) == [base / "a/ROOT"]


def test_sessions_and_theories(project: Project) -> None:
    assert list(project.sessions) == ["Base", "App-Main"]
    base = project.sessions["Base"]
    assert base.parent == "HOL"
    assert sorted(base.theories) == ["B1", "B2", "Helper", "Sub3"]
    app = project.sessions["App-Main"]
    assert sorted(app.theories) == ["A1", "Extra"]
    assert project.problems == []


def test_theory_files_are_unique(project: Project) -> None:
    files = project.theory_files()
    assert len(files) == len(set(files)) == 6


def test_session_of(project: Project) -> None:
    base = project.directory
    helper = project.session_of(base / "Base/sub/Helper.thy")
    assert helper is not None
    assert helper.name == "Base"
    assert project.session_of(base / "Base/Orphan.thy") is None


def test_unreached(project: Project) -> None:
    got = [(s.name, p.name) for s, p in project.unreached()]
    assert got == [("Base", "Orphan.thy")]


def test_resolve_import(project: Project) -> None:
    base = project.directory
    a1 = base / "App/src/A1.thy"
    app = project.sessions["App-Main"]
    assert project.resolve_import(a1, app, "Base.B2") == base / "Base/sub/B2.thy"
    assert project.resolve_import(a1, app, "../Extra") == base / "App/Extra.thy"
    assert project.resolve_import(a1, app, "HOL-Library.Multiset") is None
    assert project.resolve_import(a1, app, "~~/src/HOL/Foo") is None
    assert project.resolve_import(a1, app, "$AFP/Foo") is None
    assert project.resolve_import(a1, app, "Missing") is None
    assert project.resolve_import(a1, None, "Missing") is None


def test_keywords_follow_imports(project: Project) -> None:
    base = project.directory
    assert project.keywords_for(base / "App/src/A1.thy")["mycmd"] is CommandKind.THY_DECL
    assert "mycmd" not in project.keywords_for(base / "Base/sub/Helper.thy")
    # Cached and cycle-safe: Extra and A1 import each other.
    assert project.keywords_for(base / "App/Extra.thy")["mycmd"] is CommandKind.THY_DECL


def test_problems(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": """
session A = HOL +
  theories
    Missing
    "Other.Foo"
    "B.Nope"
    "B.X"
session B = HOL + theories X
session B = HOL + theories X
session = HOL
""",
            "X.thy": "theory X imports Main begin end",
            "Headless.thy": "(* no header *)",
        }
    )
    project = Project.load(base)
    root = base / "ROOT"
    assert project.problems == [
        Problem(root, 10, 9, "root-syntax", "expected session name"),
        Problem(root, 9, 9, "duplicate-session", "duplicate session B"),
        Problem(
            root,
            4,
            5,
            "missing-theory",
            "no Missing.thy on the search path of session A",
        ),
        Problem(root, 6, 5, "missing-theory", "session B has no theory Nope"),
    ]
    assert project.header(base / "Headless.thy") is None
    assert project.keywords_for(base / "Headless.thy")["lemma"] is CommandKind.THY_GOAL_STMT


def test_unreached_skips_nested_session_directories(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session A = HOL + directories B theories T\n"
            'session B in "B" = HOL + theories U',
            "T.thy": "theory T imports Main begin end",
            "B/U.thy": "theory U imports Main begin end",
            "B/Orphan.thy": "theory Orphan imports Main begin end",
        }
    )
    project = Project.load(base)
    assert [(s.name, p.name) for s, p in project.unreached()] == [("B", "Orphan.thy")]


def test_search_dir_may_be_missing(make_project: MakeProject) -> None:
    base = make_project({"ROOT": "session A = HOL + directories gone theories T", "T.thy": ""})
    project = Project.load(base)
    assert project.unreached() == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Foo", ("", "Foo")),
        ("HOL-Library.Multiset", ("HOL-Library", "Multiset")),
        ("../Foo", ("", "../Foo")),
        ("Common/Foo.Bar", ("", "Common/Foo.Bar")),
    ],
)
def test_split_qualified(name: str, expected: tuple[str, str]) -> None:
    assert split_qualified(name) == expected


def test_problem_is_value(tmp_path: Path) -> None:
    assert Problem(tmp_path, 1, 1, "c", "m") == Problem(tmp_path, 1, 1, "c", "m")


@pytest.mark.parametrize("roots", ["examples\ncli\n", "cli\nexamples\n", None])
def test_ownership_does_not_depend_on_discovery(
    make_project: MakeProject, roots: str | None
) -> None:
    """A theory in CLI's directory, imported by CLI and reached from a child
    session through a qualified import, belongs to CLI however the ROOT files
    are found (ROOTS in either order, or searched for)."""
    files = {
        "cli/ROOT": "session CLI = HOL + theories Run",
        "cli/Run.thy": "theory Run imports Diag begin end",
        "cli/Diag.thy": "theory Diag imports Main begin end",
        "examples/ROOT": "session Examples = CLI + theories Ex",
        "examples/Ex.thy": 'theory Ex imports "CLI.Run" begin end',
    }
    if roots is not None:
        files["ROOTS"] = roots
    base = make_project(files)
    project = Project.load(base)
    owner = project.session_of(base / "cli/Diag.thy")
    assert owner is not None
    assert owner.name == "CLI"
    assert sorted(project.owned_theories(project.sessions["Examples"])) == ["Ex"]


def test_cyclic_sessions_terminate(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOT": "session A = B + theories X\nsession B = A + theories Y",
            "X.thy": "theory X imports Main begin end",
            "Y.thy": "theory Y imports Main begin end",
        }
    )
    project = Project.load(base)
    assert sorted(project.owned_theories(project.sessions["A"])) == ["X"]
