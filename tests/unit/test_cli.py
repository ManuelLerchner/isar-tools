import runpy
import sys
from importlib.metadata import version

import pytest

from isar_tools.cli import EXIT_USAGE, main


def test_no_command_prints_help_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_USAGE
    out, err = capsys.readouterr()
    assert out == ""
    assert "usage: isar" in err


def test_unknown_command_exits_with_usage_status() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["frobnicate"])
    assert exc.value.code == EXIT_USAGE


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"isar {version('isar-tools')}"


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["isar"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("isar_tools", run_name="__main__")
    assert exc.value.code == EXIT_USAGE


def test_broken_pipe_is_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    """``isar ... | head``: a closed stdout ends the command without a traceback."""
    import argparse
    import io

    import isar_tools.cli as cli
    import isar_tools.stats.cli as stats_cli

    redirected: list[tuple[int, int]] = []

    def closed(args: argparse.Namespace) -> int:
        raise BrokenPipeError

    def fake_open(path: str, flags: int) -> int:
        return 99

    def fake_dup2(fd: int, fd2: int) -> None:
        redirected.append((fd, fd2))

    class Stdout(io.StringIO):
        def fileno(self) -> int:
            return 1

    monkeypatch.setattr(stats_cli, "run", closed)
    monkeypatch.setattr(cli.os, "open", fake_open)
    monkeypatch.setattr(cli.os, "dup2", fake_dup2)
    monkeypatch.setattr(cli.sys, "stdout", Stdout())
    assert cli.main(["stats"]) == 1
    assert redirected == [(99, 1)]
