"""Write docs/CHECKS.md and the check sections of README.md from the showcase.

docs/showcase is a small Isabelle project in which every finding is on
purpose. This runs `isar check` on it and documents each code with its first
finding: the source around it and what `isar check` prints. A code without a
finding there fails the run, unless EXEMPT says why it cannot have one, so a
new check comes with its example.

    python scripts/gen_checks.py          # rewrite the documents
    python scripts/gen_checks.py --check  # exit 1 if they are stale
"""

import ast
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOWCASE = ROOT / "docs" / "showcase"
CHECKS = ROOT / "docs" / "CHECKS.md"
README = ROOT / "README.md"
sys.path.insert(0, str(ROOT / "src"))

from isar_tools.checks.findings import CODES, DEFAULT_GROUPS, GROUPS  # noqa: E402

# Runs that together produce every finding: links need a page to read, and
# report `anchor-name` only without a build.
RUNS = [
    [*(g for g in GROUPS if g != "links"), "."],
    ["links", "site/index.md", "--browser-info", "browser_info"],
    ["links", "site/index.md"],
]
TOUR = ["proofs", "notation", "methods", "redundant", "Tour.thy"]
EXEMPT = {
    "reserved-file-name": "a file named like a Windows device (`aux.thy`) "
    "could not be checked out on Windows, so the showcase has none",
}
SUMMARIES = {
    "project": "ROOT files and the theories their sessions build.",
    "proofs": "Proofs that do not finish.",
    "syntax": "Theories Isabelle cannot load.",
    "symbols": "Characters outside ASCII.",
    "docs": "Theories, headings, locales, and classes without a text block.",
    "locales": "Free variables in locale headers.",
    "notation": "Terms written out where the project gave them a short form.",
    "unused": "Lemmas, imports, and assumptions nothing uses.",
    "redundant": "Lemmas another lemma states already.",
    "hygiene": "Characters and file names that break tools or checkouts.",
    "leftovers": "Commands of an interactive session left in.",
    "methods": "Proof methods whose arguments do nothing, and proofs to shorten.",
    "attributes": "Separate attributes that can live beside their declaration.",
    "retired": "Names the project removed that came back.",
    "prose": "Document text Isabelle does not check.",
    "links": "Links into the HTML presentation that go nowhere.",
}
# Groups with a module of their own, whose docstring explains them.
MODULES = {
    "docs": "docs",
    "locales": "locales",
    "notation": "notation",
    "unused": "unused",
    "redundant": "redundant",
    "methods": "methods",
    "attributes": "attributes",
    "retired": "retired",
    "prose": "prose",
    "links": "links",
}
FENCES = {".thy": "isabelle", ".md": "markdown"}
CONTEXT = 3  # lines shown on each side of a finding
# PyPI renders the README too, so its links are absolute.
GITHUB = "https://github.com/ManuelLerchner/isar-tools/blob/main"


def run(args: list[str]) -> list[dict[str, str | int]]:
    result = subprocess.run(
        [sys.executable, "-m", "isar_tools", "check", *args, "--format", "json"],
        cwd=SHOWCASE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"},
        check=False,
    )
    if result.returncode not in (0, 1):
        sys.exit(f"isar check {' '.join(args)}: exit {result.returncode}\n{result.stderr}")
    return json.loads(result.stdout)["findings"]


def line_of(finding: dict[str, str | int]) -> str:
    where = f"{finding['path']}:{finding['line']}:{finding['column']}"
    return f"{where}: {finding['code']}: {finding['message']}"


def visible(text: str) -> str:
    """``text`` with control and formatting characters spelled out."""
    return "".join(
        f"\\u{ord(c):04x}" if unicodedata.category(c) in ("Cc", "Cf") and c != "\t" else c
        for c in text
    ).replace("\t", "\\t")


def excerpt(finding: dict[str, str | int]) -> tuple[str, str]:
    """The fence language and the lines around a finding: its paragraph, at
    most CONTEXT lines on each side."""
    path = SHOWCASE / str(finding["path"])
    lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    at = int(finding["line"]) - 1
    start = at
    while start > max(0, at - CONTEXT) and lines[start - 1].strip():
        start -= 1
    end = at
    while end < min(len(lines) - 1, at + CONTEXT) and lines[end + 1].strip():
        end += 1
    language = FENCES.get(path.suffix, "isabelle" if path.name in ("ROOT", "ROOTS") else "text")
    return language, "\n".join(visible(line.rstrip("\r")) for line in lines[start : end + 1])


def docstring(module: str) -> str:
    """The module's docstring after its first paragraph, as Markdown."""
    source = (ROOT / "src" / "isar_tools" / "checks" / f"{module}.py").read_text("utf-8")
    text = ast.get_docstring(ast.parse(source)) or ""
    body = text.split("\n\n", 1)[1] if "\n\n" in text else ""
    body = re.sub(r"``(.+?)``", r"`\1`", body)
    return re.sub(r"(?<![*\w`])\*(\w[^*`]*?)\*(?![*\w])", r"_\1_", body).strip()


def codes_of(group: str) -> list[str]:
    return [code for code, (g, _) in CODES.items() if g == group]


def table(header: list[str], rows: list[list[str]]) -> str:
    """A Markdown table with aligned columns, as prettier writes it."""
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)) + " |"

    return "\n".join([line(header), line(["-" * w for w in widths]), *map(line, rows)])


def groups_table(link: str) -> str:
    rows = [
        [
            f"[`{group}`]({link}#{group})",
            ", ".join(f"`{c}`" for c in codes_of(group)),
            "by default" if group in DEFAULT_GROUPS else "when named",
        ]
        for group in GROUPS
    ]
    return table(["Group", "Codes", "Runs"], rows)


def checks_document(first: dict[str, dict[str, str | int]]) -> str:
    out = [
        "# Checks",
        "",
        "<!-- Generated by scripts/gen_checks.py from docs/showcase; do not edit. -->",
        "",
        "`isar check [GROUP...] [PATH...]` runs the groups `project`, `proofs`, and "
        "`syntax` unless named others. Each example below is a finding on the "
        "[showcase project](showcase), which holds one for every code.",
        "",
        "A comment `(* isar-ignore *)` after code silences every finding on its line; "
        "alone on a line, it silences the next line. `(* isar-ignore: oops, tab *)` "
        "silences only those codes. `--ignore CODE` drops a code everywhere, and "
        "`--allow NAME` (or `check.allow`) accepts a name in `locales`, `notation`, "
        "`prose`, and `unused`.",
        "",
        groups_table(""),
    ]
    for group in GROUPS:
        out += ["", f"## {group}", "", SUMMARIES[group]]
        if group in MODULES:
            out += ["", docstring(MODULES[group])]
        for code in codes_of(group):
            out += ["", f"### `{code}`", "", CODES[code][1][0].upper() + CODES[code][1][1:] + "."]
            if code in EXEMPT:
                out += ["", f"No example: {EXEMPT[code]}."]
                continue
            finding = first[code]
            language, text = excerpt(finding)
            out += [
                "",
                f"`{finding['path']}`:",
                "",
                f"```{language}",
                text,
                "```",
                "",
                "```console",
                visible(line_of(finding)),
                "```",
            ]
    return "\n".join(out) + "\n"


def tour_section() -> str:
    text = (SHOWCASE / "Tour.thy").read_text("utf-8").rstrip()
    findings = run(TOUR)
    return "\n".join(
        [
            "```isabelle",
            text,
            "```",
            "",
            "```console",
            f"$ isar check {' '.join(TOUR)}",
            *(line_of(f) for f in findings),
            "```",
        ]
    )


def replace_section(text: str, name: str, body: str) -> str:
    begin, end = f"<!-- {name}:begin -->", f"<!-- {name}:end -->"
    if begin not in text or end not in text:
        sys.exit(f"README.md: no {begin} ... {end} section")
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{begin}\n\n{body}\n\n{end}{tail}"


def main() -> int:
    first: dict[str, dict[str, str | int]] = {}
    for args in RUNS:
        for finding in sorted(run(args), key=lambda f: (str(f["path"]), int(f["line"]))):
            first.setdefault(str(finding["code"]), finding)
    missing = sorted(set(CODES) - set(first) - set(EXEMPT))
    if missing:
        sys.exit(f"no finding in docs/showcase for: {', '.join(missing)}")
    documents = {
        CHECKS: checks_document(first),
        README: replace_section(
            replace_section(README.read_text("utf-8"), "tour", tour_section()),
            "groups",
            groups_table(f"{GITHUB}/docs/CHECKS.md"),
        ),
    }
    stale = [p for p, text in documents.items() if not p.exists() or p.read_text("utf-8") != text]
    if "--check" in sys.argv[1:]:
        for path in stale:
            print(
                f"{path.relative_to(ROOT).as_posix()} is stale; run scripts/gen_checks.py",
                file=sys.stderr,
            )
        return 1 if stale else 0
    for path, text in documents.items():
        path.write_text(text, "utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
