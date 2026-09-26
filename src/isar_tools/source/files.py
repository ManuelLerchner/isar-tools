"""Byte-exact reading and writing of source files.

``Path.read_text`` translates ``\\r\\n`` to ``\\n``, which would silently change
line endings of any file a tool rewrites. These helpers decode and encode
UTF-8 without newline translation.
"""

from pathlib import Path


def read_source(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def write_source(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))
