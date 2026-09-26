import runpy
import sys

import pytest

from isar_tools import __version__
from isar_tools.cli import COMMANDS, EXIT_USAGE, main


def test_no_command_prints_help_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_USAGE
    out, err = capsys.readouterr()
    assert out == ""
    assert "usage: isar" in err


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_placeholder_commands_fail_with_usage_status(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([command]) == EXIT_USAGE
    out, err = capsys.readouterr()
    assert out == ""
    assert f"isar {command}: not implemented yet" in err


def test_unknown_command_exits_with_usage_status() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["frobnicate"])
    assert exc.value.code == EXIT_USAGE


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"isar {__version__}"


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["isar"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("isar_tools", run_name="__main__")
    assert exc.value.code == EXIT_USAGE
