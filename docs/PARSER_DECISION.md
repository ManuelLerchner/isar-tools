# Parser decision: isabelle-layout and isabelle-query

Spike date 2026-09-26. File:line references point into the unpacked 0.2.2 and 0.9.2 wheels.
Corpora: all 1027 ROOTs of the AFP mirror for Isabelle2025-2 (commit `cfdc3d77`) and the
Voblint repository. The throwaway experiment scripts are not committed. Isabelle was not
installed, so nothing below has been checked against `isabelle build` or `isabelle sessions`.

## Question

Can isar-tools (formatter, project checks, statistics) reuse `isabelle-layout 0.2.2` or
`isabelle-query 0.9.2` instead of its own ROOT reader and `.thy` lexer? In particular, does
either package expose a lossless token or span model that a formatter can print back
byte-for-byte?

## isabelle-layout 0.2.2

**Provides**

- A public API pinned by `__all__` (`__init__.py:78-90`): `discover_roots`, `iter_sessions`,
  `parse_root_sessions`, `resolve_session_theory`, `session_theories`, `parse_thy_imports`,
  `iter_thy_files`, `resolve_base_logic`, `default_t_dir`, and `SessionInfo`.
- `discover_roots` follows `ROOTS` recursively like `isabelle build -D`, else walks for `ROOT`
  (`roots.py:442-510`).
- `SessionInfo` fields `name, root_path, in_subdir, parent, used_sessions, directories,
theories` (`roots.py:219-227`). Theory entries stay raw, so qualified
  (`"HOL-Computational_Algebra.Euclidean_Algorithm"`) and path (`"d1/Y"`) entries survive.
- ROOT tokenizer (`roots.py:262-307`) over text with nested `(* *)`, nested cartouches and
  `{* *}` stripped first (`_lexer.py:51-123`); `[...]`/`(...)` groups skipped whole.
- `parse_thy_imports`: regex over the whole comment-stripped file, anchored on
  `theory NAME imports ... (begin|keywords|abbrevs)` (`theories.py:193-231`).
- `session_theories`: declared theories plus in-entry import closure (`theories.py:405-465`).
- Conformance corpus as package data (`data/conformance.json`, 8 cases, verdicts from
  Isabelle2025-2; not re-run here).

**Does not provide**

- Source positions: `SessionInfo` has no line or column; offsets are dropped
  (`roots.py:282,307`).
- Values of `options`, `description`, `chapter`, `document_files`, `export_files`,
  `document_theories` (ignored, `roots.py:398`).
- Header details: `parse_thy_imports` returns import names only (no theory name, header span,
  `keywords` or `abbrevs`).
- Diagnostics: malformed input degrades silently.

**Gets wrong (synthetic probes)**

- `_ID_RE = [A-Za-z0-9_./\-]+` (`roots.py:259`) drops `'`: `session A' = HOL + theories T'`
  gives session `A`, theory `T`. Symbols are blanked (`_lexer.py:122`): `"A\<^sub>1"` → `"A 1"`.
- An unterminated string or comment silently truncates the ROOT (`roots.py:279-281`):
  `theories "X` then `session B` yields only session A, no theories, no error.
- `theory \<open>Q\<close> imports A begin` gives `[]` (cartouche stripped before the regex).
- `resolve_session_theory` falls back to a unique `rglob` match (`roots.py:437-439`), which
  Isabelle does not do. `iter_thy_files` uses a line-oriented first-session-only reader when
  `t_dir/ROOT` exists (`roots.py:76-103`, `theories.py:257-262`).
- `session_theories` silently drops declared entries with no local file, including every
  qualified entry (Voblint: 243 declared, 241 kept). Some reads use the locale encoding
  (`roots.py:90,501`, `project.py:115`).

**Corpus runs**

| Corpus         | ROOTs | Sessions | Exceptions | Anonymous or parentless | Declared theories | Unresolved (+ qualified) | Closure               | Time                     |
| -------------- | ----- | -------- | ---------- | ----------------------- | ----------------- | ------------------------ | --------------------- | ------------------------ |
| Voblint        | 28    | 28       | 0          | 0                       | 243               | 0 (+3)                   | 241                   | <0.1 s                   |
| AFP, all ROOTs | 1027  | 1057     | 0          | 0                       | 5497              | 0 (+87)                  | 10344 of 10418 `.thy` | 0.3 s parse, 9 s closure |

As a cross-check, we compared each ROOT's count of `^\s*session\s` lines with the parser's
session count. They differ in 1 of 1027 ROOTs: `Security_Protocol_Refinement` has 6 such lines
but 1 parsed session. The other 5 lines are inside a `(* *)` block, so the parser is right.
Every theory in the closure had a non-empty `imports`. Voblint has no top-level `ROOT`;
its 28 ROOT files are found through `ROOTS`.

## isabelle-query 0.9.2

**Provides**

- The supported surface is `isabelle_query.api`, with
  `__all__ = ["Entry", "TheorySection", "parse_root", "parse_theory"]` (`api.py:77`).
  Everything else is declared internal (`__init__.py:12-18`, `api.py:25-53`).
- `TheorySection` (`model.py:196-346`): `source()` (= `read_text().splitlines()`); line
  ranges `text_blocks`, `heading_spans`, `comment_ranges`, `nonisar_ranges`, `outline`;
  per-line column masks `nonisar_spans` (comments, `{* *}`, formal-comment cartouches, ML
  bodies) and `inner_spans` (those plus strings and cartouches); and the length-preserving
  blanked views `live_source()` and `outer_source()`.
- `Entry` (`model.py:67-193`) covers declaration commands only (`DECL_RE`,
  `parsing.py:46-48`, plus header-declared custom commands), with line numbers `thy_line`,
  `decl_end_line`, `proof_line`, `body_end_line`, `thy_end`, `preamble`.
- Internally a character-level state machine (`parsing.py:1615-1776`) handles nested
  comments and cartouches, `\"`/`\\` escapes and formal-comment markers, and classifies ML
  bodies by the preceding command keyword.

**Does not provide a lossless token model**

- No token stream and no command-span list. The spans are unlabelled masks over raw lines: a
  string cannot be told from a cartouche, nor a comment from an ML body. Non-declaration
  commands (`declare`, `lemmas`, `context`, `end`, `text`, `ML`, proof commands) are only
  internal boundaries (`parsing.py:2305-2383`).
- `source()` loses newline style and the final newline; `splitlines()` also splits on
  `\x0b \x0c \x1c-\x1e \x85 \u2028 \u2029` (no AFP file contains these).
- Backquoted fact literals `` `...` `` are not recognised as inner syntax.
- `keywords` is found only at the start of a line (`parsing.py:1042,1117-1137`); no AFP file
  puts it mid-line, so the defect is latent.
- The custom-command table is a module global (`parsing.py:110`): not re-entrant.

**Round-trip experiment.** The sample was 200 random AFP `.thy` files
(seed 0) plus all 241 Voblint files. With no token stream, the only thing to rebuild the file
from is the `source()` lines. The span masks are slices of those same lines and add nothing.

| Check                                                                               | AFP 200    | Voblint 241 |
| ----------------------------------------------------------------------------------- | ---------- | ----------- |
| Parse exceptions                                                                    | 0          | 0           |
| `"\n".join(source())+"\n"` equals the file (only information the API gives)         | 143/200    | 241/241     |
| Same, but the final `\n` is added only if the original had one (needs the original) | 197/200    | 241/241     |
| Same, after normalising CR and CRLF to LF                                           | 200/200    | 241/241     |
| Entry spans `[src_start, thy_end]` are disjoint                                     | 199/200    | 241/241     |
| Share of non-blank lines inside some entry span (median, min)                       | 0.90, 0.00 | 0.85, 0.00  |
| Comment, string, and cartouche endpoints agree with a reference lexer               | 199/200    | 240/241     |

Every lexer disagreement came from a backquoted `` `...` `` fact (`Bit_Counting.thy:77`,
`Congruence_Lattice.thy:281`). Across the whole AFP, 2825 of 10418 files have no final newline
and 146 contain `\r`. Parsing the 200 AFP files took 1.7 s.

**Custom keywords.** A command declared in a theory header is recognised in
that theory. In other theories, `parse_root` recognises it, but `parse_theory` does not
(documented at `api.py:89-94`). A `keywords` clause on the same line as `theory` or
`imports` is missed by both.

## Stability and packaging

|                        | isabelle-layout                                                                     | isabelle-query                                                                         |
| ---------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| PyPI releases          | 0.2.2 only (2026-08-11)                                                             | 6 releases: 0.6.7 (2026-08-11) to 0.9.2 (2026-09-26)                                   |
| Stability promise      | test pins `__all__`; `SessionInfo` field names promised; removals need a minor bump | 4 names in `api`; breaking changes need a minor bump (`api.py:27-30`)                  |
| Runtime deps           | none (stdlib only)                                                                  | `isabelle-layout>=0.2.2`                                                               |
| Python floor / license | `>=3.9` / MIT                                                                       | `>=3.9` / MIT                                                                          |
| Wheel                  | `py3-none-any`, hatchling, JSON package data                                        | `py3-none-any`, hatchling, ships a `.ML` file                                          |
| Side effects           | reads `ISABELLE_LAYOUT_ROOT` / `ISABELLE_QUERY_ROOT` in `default_t_dir`             | may run the `isabelle` binary (`_namespace_resolve.py:38-91`; CLI features, not `api`) |
| noarch-friendly        | yes                                                                                 | yes                                                                                    |
| conda-forge            | unverified                                                                          | unverified                                                                             |

Both packages are single-author and classified "Development Status :: 4 - Beta". The upstream
GitHub repositories (`ott2/*`) could not be reached, so their tests, CI, and issue history are
unverified.

## Decision

1. **Reuse isabelle-layout for ROOT and session discovery, behind a thin adapter.** It raised
   no exceptions on all 1027 AFP ROOTs and 28 Voblint ROOTs. It has no dependencies and an MIT
   license. The adapter should let us add positions and diagnostics, report the silent
   truncation and `'`-dropping cases, and replace the package locally if its 0.x API changes.
   Run the shipped conformance corpus in our tests.
2. **Do not depend on isabelle-query for parsing.** Its public API works at the level of
   declarations and whole lines. Its masks are unlabelled, and it exposes neither tokens nor
   command spans. It is also a fast-moving 0.x CLI package, a heavy dependency for four names.
3. **The formatter needs its own lossless lexer**: over the source text with original
   newlines, typed tokens with offsets (whitespace, nested comment, nested cartouche, string,
   alt-string, verbatim, symbol, word, other), invariant `"".join(tokens) == source`, and
   command segmentation on top from Pure's built-in keywords plus header `keywords` clauses in
   any position. A ~50-line throwaway prototype tokenised all 441 sampled files with
   no unterminated regions; it is lossless whenever it covers every character.
4. Checks that need imports can use either our lexer (header tokens, with positions) or
   `isabelle_layout.parse_thy_imports` (names only).

### Revision after implementation (M1)

Point 1 was reversed: isar-tools parses ROOT files itself (`project/root.py`) on the shared
lexer, and does not depend on isabelle-layout. Reasons:

- The adapter would have had to re-lex every ROOT anyway to supply positions and to detect
  the silent truncation and `'`-dropping cases, so it would duplicate the parser it wraps.
- With the shared lexer, an unquoted `HOL-Library` or `Common/Foo` is several tokens, exactly
  as in Isabelle, so the parser reports it instead of accepting or mangling it.
- One fewer dependency keeps the conda-forge path to a single `noarch: python` package.

Evidence: the parser reads all 1027 AFP ROOTs reached through `ROOTS` and all 28 Voblint ROOTs
with no diagnostics, finds 1057 AFP sessions (isabelle-layout: 1057), and the project model
reaches 10342 AFP theories (isabelle-layout's closure: 10344; not yet reconciled). The opt-in
corpus tests (`tests/corpus`) keep this checked.

The same run corrected a Voblint assumption: quoted slash entries such as
`"Common/List_Misc"` are valid (911 of them in the AFP). Only the unquoted spelling fails,
because it is several tokens.

## Open questions

- Do either package's results agree with real Isabelle (`isabelle sessions`,
  `isabelle build -n -l`)? Unverified; the README's probe over 988 AFP and 132 distribution
  sessions is also unverified.
- Are `'` or symbols legal, or used, in session and theory names? Unverified. No AFP ROOT
  theory entry contains `'`.
- Is `session A` with no `= PARENT` legal in Isabelle2025-2? layout accepts it with
  `parent=None`. Unverified.
- Is either package on conda-forge? Unverified. Upstream tests, CI, and maintenance: unverified.
- How the reference lexer should treat `\<^cancel>`, `\<comment>`, and antiquotations needs
  checking against `Pure/Isar/token.ML` before the formatter relies on it.
