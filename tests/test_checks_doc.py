import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_checks_doc_is_current() -> None:
    """docs/CHECKS.md and the README's check sections match docs/showcase, and
    every code has an example there."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_checks.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
