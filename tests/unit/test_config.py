from pathlib import Path

import pytest

from isar_tools.config import Config, ConfigError, Exclude, find, load, parse
from tests.conftest import MakeProject


@pytest.mark.parametrize(
    ("glob", "path", "expected"),
    [
        ("src/**/generated/**", "src/a/generated/X.thy", True),
        ("src/**/generated/**", "src/generated/X.thy", True),
        ("src/**/generated/**", "src/a/gen/X.thy", False),
        ("src/*.thy", "src/X.thy", True),
        ("src/*.thy", "src/a/X.thy", False),
        ("vendor", "vendor/td/X.thy", True),  # a directory excludes what is below it
        ("/vendor/", "vendor/td/X.thy", True),
        ("X?.thy", "X1.thy", True),
        ("X?.thy", "X12.thy", False),
        ("a+b.thy", "a+b.thy", True),  # regex characters are literal
    ],
)
def test_exclude_globs(tmp_path: Path, glob: str, path: str, expected: bool) -> None:
    assert Exclude(tmp_path, glob).matches(tmp_path / path) is expected


def test_exclude_outside_its_base(tmp_path: Path) -> None:
    assert not Exclude(tmp_path / "a", "**").matches(tmp_path / "b" / "X.thy")


def test_find_isar_toml_before_pyproject(make_project: MakeProject) -> None:
    base = make_project(
        {
            "pyproject.toml": "[tool.isar]\nexclude = ['x']\n",
            "sub/isar.toml": "exclude = ['y']\n",
            "sub/deeper/.keep": "",
        }
    )
    found = find(base / "sub" / "deeper")
    assert found == (base / "sub" / "isar.toml", {"exclude": ["y"]})
    assert find(base) == (base / "pyproject.toml", {"exclude": ["x"]})


def test_pyproject_without_tool_isar_is_skipped(make_project: MakeProject) -> None:
    base = make_project({"pyproject.toml": "[tool.other]\nx = 1\n", "a/.keep": ""})
    found = find(base / "a")
    assert found is None or found[0] != base / "pyproject.toml"


def test_parse_everything(
    make_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = make_project({"afp/thys/.keep": "", "vendor/.keep": ""})
    monkeypatch.setenv("AFP", str(base / "afp" / "thys"))
    monkeypatch.delenv("UNSET_ISAR_VAR", raising=False)
    config = parse(
        base / "isar.toml",
        {
            "include": ["$AFP", "vendor", "missing", "$UNSET_ISAR_VAR"],
            "exclude": ["gen/**"],
            "fmt": {"max-line-length": 100, "normalize": True},
            "check": {"groups": ["proofs"], "ignore": ["oops"], "allow": ["n"]},
            "stats": {"max-line-length": 80, "watch": ["metis"]},
        },
    )
    assert config.include == [base / "afp" / "thys", base / "vendor"]
    assert config.exclude == [Exclude(base, "gen/**")]
    assert config.fmt == {"max-line-length": 100, "normalize": True}
    assert config.check == {"groups": ["proofs"], "ignore": ["oops"], "allow": ["n"]}
    assert config.stats == {"max-line-length": 80, "watch": ["metis"]}
    err = capsys.readouterr().err
    assert "include 'missing': not a directory here; skipped" in err
    assert "include '$UNSET_ISAR_VAR'" in err


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ({"nope": 1}, "unknown option 'nope'"),
        ({"include": "x"}, "include: expected a list of strings"),
        ({"exclude": [1]}, "exclude: expected a list of strings"),
        ({"fmt": 1}, "[fmt] must be a table"),
        ({"fmt": {"width": 1}}, "[fmt] has no option 'width'"),
        ({"fmt": {"indent": "2"}}, "fmt.indent: expected int"),
        ({"fmt": {"indent": True}}, "fmt.indent: expected int"),
        ({"fmt": {"normalize": 1}}, "fmt.normalize: expected bool"),
        ({"check": {"groups": ["nope"]}}, "check.groups: unknown group 'nope'"),
        ({"check": {"ignore": ["nope"]}}, "check.ignore: unknown code 'nope'"),
        ({"stats": {"watch": "metis"}}, "stats.watch: expected a list of strings"),
    ],
)
def test_parse_errors(tmp_path: Path, table: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("]", r"\]")):
        parse(tmp_path / "isar.toml", table)


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"isar.toml": "[broken"}, "isar.toml"),
        ({"pyproject.toml": "[tool]\nisar = 1\n"}, "[tool.isar] must be a table"),
    ],
)
def test_unreadable(make_project: MakeProject, files: dict[str, str], message: str) -> None:
    base = make_project(files)
    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("]", r"\]")):
        load(base)


def test_no_file_is_an_empty_config(tmp_path: Path) -> None:
    config = load(tmp_path)
    assert config.path is None or config.path.parent != tmp_path
    assert Config().include == []
