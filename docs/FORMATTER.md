# The formatter

`isar fmt` formats Isabelle theory files. This document states what it
guarantees, which layout it produces, and what it deliberately leaves alone.

## Guarantees

- **Only layout changes.** The formatter changes the whitespace at the start of
  a line, removes trailing whitespace, collapses runs of blank lines, and, with
  `--max-line-length`, turns a space between two tokens into a line break.
  Isabelle's outer syntax treats all of these alike, so the prover reads the
  same token sequence.
- **Opaque regions stay byte-identical.** Strings, cartouches (document text,
  ML, inner syntax), comments, and verbatim blocks are single tokens and are
  never rewritten. A line that starts such a token and continues it on later
  lines keeps its indentation, so the continuation lines stay aligned with it.
- **Idempotence.** Formatting formatted text changes nothing.
- **Line endings** are preserved; a CRLF file stays CRLF.
- **Refusal instead of guessing.** A file with an unterminated comment, string,
  cartouche, or verbatim block is not formatted (exit status 2), since the
  extent of the unterminated region is unknown.

How this is checked:

- by construction: the formatter only replaces whitespace tokens;
- property tests (Hypothesis) over generated theory-like text with random
  options: formatted output has the same non-whitespace tokens as the input and
  is a fixed point;
- golden tests (`tests/formatter/input` → `expected`, `expected-normalize`);
- corpus tests over all theories of the AFP and of Voblint (`pixi run corpus`).

None of this runs Isabelle, so a formatted file is not verified to build. The
check for that is a round trip in a project's own CI: format the sources, then
run `isabelle build`.

## Indentation

Indentation follows the proof structure, computed from each command's kind as
Isabelle declares it:

| Line                                                                               | Indentation                             |
| ---------------------------------------------------------------------------------- | --------------------------------------- |
| theory-level command (`lemma`, `definition`, `text`, ...)                          | column 0                                |
| `proof`, `next`, `qed`                                                             | the goal they prove                     |
| command inside a `proof ... qed` or `{ ... }` block                                | one step deeper than the block          |
| refinement of a goal (`using`, `unfolding`, `apply`, `by`, `done`, ...)            | one step deeper than the goal statement |
| `using ... proof (...)` on one line                                                | as its `proof`                          |
| clause (`fixes`, `assumes`, `shows`, `obtains`, `for`, `if`, ...) outside brackets | one step deeper than its command        |
| `and`                                                                              | deeper than its clause                  |
| `begin` of a command such as `context ... begin`                                   | as its command                          |
| any other continuation line                                                        | same offset from its command as before  |

One step is `--indent` columns (default 2). Example:

```isabelle
lemma foo:
  assumes "A"
    and "B"
  shows "C"
proof -
  have h: "D"
    using assms
    by auto
  show ?thesis
    using h
    by auto
qed
```

### Raise-only by default

Projects differ in indent width and alignment (4-space steps, `and`
right-aligned under `assumes`, ...). By default the formatter therefore only
raises lines that are indented less than their structure requires and keeps any
deeper indentation. `--normalize` sets every structural line exactly.

### What is kept in either mode

- **Apply scripts.** Their indentation often encodes the number of open
  subgoals, which only the prover knows. Lines of an apply script keep their
  offsets from its first line; the script as a whole moves only as far as its
  first line must.
- **Theory commands inside `begin ... end` blocks** (`context`, `locale`,
  `instantiation`, ...). Whether these are indented is a project's choice.
- **Lines that start with a comment.**
- **`where`** is not treated as a clause: projects place it in too many ways.

Commands not known to the formatter (from a session neither built in nor passed
with `-d`) are read as continuation lines of the previous command and keep their
relative offset.

## Blank lines and whitespace

- Trailing whitespace is removed from every line, except inside multi-line
  tokens.
- Runs of blank lines longer than `--max-blank-lines` (default 2) are
  shortened; blank lines at the start of the file are removed.
- The file ends with exactly one line break.

## Line wrapping

With `--max-line-length N` (off by default), a line longer than N Isabelle
symbols (`\<Longrightarrow>` counts as one) is broken at a space between two
tokens:

1. before a command later on the line, so `have "..." using a by simp` becomes
   one command per line, indented by structure;
2. otherwise at the shallowest bracket depth, at the rightmost space where the
   first part fits; the rest goes one step deeper than the line it came from.

There is never a break between a command keyword and its first argument, and
every break must shorten the line. A line that cannot be shortened, such as a
single long string, stays as it is. Wrapping repeats until nothing changes; it
terminates because every round splits a line into two non-empty lines.

## Options

| Option                | Default | Meaning                                                |
| --------------------- | ------- | ------------------------------------------------------ |
| `--check`             |         | list files that would change; exit 1 if any            |
| `--diff`              |         | print a unified diff instead of writing; exit 1 if any |
| `--normalize`         | off     | set indentation exactly instead of only raising it     |
| `--indent N`          | 2       | indent step                                            |
| `--max-blank-lines N` | 2       | longest run of blank lines kept                        |
| `--max-line-length N` | off     | wrap longer lines                                      |
| `-d DIR`              |         | read commands declared by the sessions of DIR          |
| `--color`             | auto    | colour `--diff` output                                 |
