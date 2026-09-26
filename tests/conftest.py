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
