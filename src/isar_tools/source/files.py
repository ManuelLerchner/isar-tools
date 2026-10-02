"""Byte-exact reading and writing of source files.

``Path.read_text`` translates ``\\r\\n`` to ``\\n``, which would silently change
line endings of any file a tool rewrites. These helpers decode and encode
UTF-8 without newline translation.
"""

from pathlib import Path


def read_source(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def read_lenient(path: Path) -> str:
    """The text of ``path`` for analysis only: bytes that are not UTF-8 become
    U+FFFD, so one such file does not stop a check of the whole project
    (``isar check`` reports it as ``invalid-utf8``)."""
    return path.read_bytes().decode("utf-8", errors="replace")


def write_source(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))
