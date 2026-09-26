import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

import pytest

MakeProject: TypeAlias = Callable[[dict[str, str]], Path]


@pytest.fixture
def make_project(tmp_path: Path) -> MakeProject:
    """Write ``{relative path: content}`` below a fresh directory; return it."""

    def make(files: dict[str, str]) -> Path:
        for rel, content in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return tmp_path.resolve()

    return make


GOLDEN_DIR = Path(__file__).parent / "golden"
Golden: TypeAlias = Callable[[str, str], None]


@pytest.fixture
def golden() -> Golden:
    """Compare text with ``tests/golden/<name>``.

    With ``UPDATE_GOLDEN=1`` the file is (re)written instead, so a change in
    output shows up as a diff in review.
    """

    def check(name: str, actual: str) -> None:
        path = GOLDEN_DIR / name
        if os.environ.get("UPDATE_GOLDEN") == "1":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual, encoding="utf-8", newline="\n")
            return
        assert path.is_file(), f"missing golden file {path}; run with UPDATE_GOLDEN=1"
        assert actual == path.read_text(encoding="utf-8")

    return check
