"""Run the `isar` commands of the README demo tape without recording them.

Reads every `Type "isar ..."` line of docs/demo/demo.tape, runs it in the
demo project, and fails if a command crashes or exits with an unexpected
status. `isar check` and `--diff`/`--check` report findings with exit status 1;
every other command must exit 0. The demo project must be left unchanged.
"""

import hashlib
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAPE = ROOT / "docs" / "demo" / "demo.tape"
PROJECT = ROOT / "docs" / "demo" / "project"
TYPE = re.compile(r'^Type "(isar .*)"$')
WRITES = ("fmt", "normalize")


def snapshot() -> dict[Path, str]:
    return {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(PROJECT.rglob("*"))
        if path.is_file()
    }


def allowed_statuses(argv: list[str]) -> set[int]:
    if argv[1] == "check" or "--diff" in argv or "--check" in argv:
        return {0, 1}
    return {0}


def run(command: str) -> str | None:
    argv = shlex.split(command)
    if any(word in argv for word in WRITES) and not {"--diff", "--check"} & set(argv):
        return f"{command}: would rewrite the demo project; use --diff or --check"
    result = subprocess.run(
        [sys.executable, "-m", "isar_tools", *argv[1:]],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )
    if "Traceback" in result.stderr or result.returncode not in allowed_statuses(argv):
        return f"{command}: exit status {result.returncode}\n{result.stderr}"
    return None


def main() -> int:
    lines = TAPE.read_text(encoding="utf-8").splitlines()
    commands = [m.group(1) for m in map(TYPE.match, lines) if m]
    if not commands:
        print(f"{TAPE.relative_to(ROOT).as_posix()}: no `isar` commands found", file=sys.stderr)
        return 1
    before = snapshot()
    failures = [failure for failure in map(run, commands) if failure]
    if snapshot() != before:
        failures.append("docs/demo/project changed while running the demo commands")
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print(f"{len(commands)} demo commands ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
