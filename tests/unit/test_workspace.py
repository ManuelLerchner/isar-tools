import pytest

from isar_tools.project.workspace import NO_SESSION, InputError, collect, load, project_root
from isar_tools.source.keywords import CommandKind
from tests.conftest import MakeProject

FILES = {
    "ROOT": "session S = HOL + directories sub theories A",
    "A.thy": 'theory A imports B keywords "kw" :: diag begin end',
    "sub/B.thy": "theory B imports Main begin end",
    "loose/C.thy": "theory C imports Main begin\nkw\nend",
    ".git/D.thy": "",
    "notes.txt": "",
}


def test_directory(make_project: MakeProject) -> None:
    base = make_project(FILES)
    sources = collect([base])
    assert [(s.path.relative_to(base).as_posix(), s.session) for s in sources] == [
        ("A.thy", "S"),
        ("loose/C.thy", NO_SESSION),
        ("sub/B.thy", "S"),
    ]
    a = sources[0]
    assert a.keywords()["kw"] is CommandKind.DIAG
    assert a.read().startswith("theory A")
    assert [c.name for c in a.parse().commands] == ["theory", "end"]


def test_directory_twice_is_one_project(make_project: MakeProject) -> None:
    base = make_project(FILES)
    workspace = load([base, base])
    assert len(workspace.projects) == 1
    assert len(workspace.sources) == 3


def test_file_arguments_add_no_projects(make_project: MakeProject) -> None:
    base = make_project(FILES)
    assert load([base / "A.thy"]).projects == []


def test_files_use_the_nearest_project(make_project: MakeProject) -> None:
    base = make_project(FILES)
    sources = collect([base / "sub/B.thy", base / "sub/B.thy", base / "A.thy"])
    assert [(s.path.name, s.session) for s in sources] == [("B.thy", "S"), ("A.thy", "S")]
    assert sources[0].project is sources[1].project


def test_project_root(make_project: MakeProject, tmp_path_factory: pytest.TempPathFactory) -> None:
    base = make_project(FILES)
    assert project_root(base / "sub/B.thy") == base
    orphan = tmp_path_factory.mktemp("orphan") / "x" / "y.thy"
    assert project_root(orphan) == orphan.parent


def test_project_root_climbs_to_the_roots_listing_it(make_project: MakeProject) -> None:
    base = make_project(
        {
            "ROOTS": "lib\nmain\n",
            "lib/ROOT": "session L = HOL + theories L",
            "lib/L.thy": "theory L imports Main begin end",
            "main/ROOT": "session M = L + theories M",
            "main/M.thy": "theory M imports L begin end",
            "vendor/ROOT": "session V = HOL + theories V",
            "vendor/V.thy": "theory V imports Main begin end",
        }
    )
    assert project_root(base / "lib/L.thy") == base
    assert project_root(base / "vendor/V.thy") == base / "vendor"  # not listed


@pytest.mark.parametrize(
    ("name", "message"),
    [("notes.txt", "not a directory or .thy file"), ("missing", "no such file or directory")],
)
def test_bad_paths(make_project: MakeProject, name: str, message: str) -> None:
    base = make_project(FILES)
    with pytest.raises(InputError, match=message):
        collect([base / name])


def test_included_directories_inside_a_project_are_not_its_files(
    make_project: MakeProject,
) -> None:
    """An AFP or submodule inside the project is passed with -d to resolve
    against; its theories are not the project's to check or format."""
    base = make_project(
        {
            **FILES,
            "afp/thys/ROOTS": "E",
            "afp/thys/E/ROOT": "session E = HOL + theories E",
            "afp/thys/E/E.thy": "theory E imports Main begin end",
            ".git/modules/x/ROOT": "",  # not a project, whatever it holds
        }
    )
    # Without -d it is another project nested in this one: skipped, with a note.
    workspace = load([base])
    assert [p.relative_to(base).as_posix() for p in workspace.skipped] == ["afp/thys"]
    assert "afp/thys/E/E.thy" not in [
        s.path.relative_to(base).as_posix() for s in workspace.sources
    ]
    sources = collect([base], [base / "afp" / "thys"])
    assert [s.path.relative_to(base).as_posix() for s in sources] == [
        "A.thy",
        "loose/C.thy",
        "sub/B.thy",
    ]
    # A directory that is itself included is still read when named.
    assert [s.path.name for s in collect([base / "afp"], [base / "afp"])] == ["E.thy"]
