---
title: Gotcha - A Comment Pass Is Not a Find-and-Replace
type: gotcha
tags: [gotcha, comments, style, tooling, tests, guard, unicode, refactor]
status: fixed — 2026-09-04. 249 status emoji and 812 bold spans removed from comments across
  ~250 files; `tools/comment_style.py` is the fixer and `tests/test_comment_style.py` the guard.
  Both share one scanner. CLAUDE.md's Writing style section carries the rules.
cache-version: n/a — comments and documentation only. No engine, extraction or `render_bounds`
  change, and both suites were run green after every pass.
related: [Gotcha - The Prototype Build Was Prototype By Accident, Gotcha - A Guard Test's Failure
  Path Had Never Run, Gotcha - Three Quoted Figures That No Command Could Reproduce]
date: 2026-09-04
---

# Gotcha — A Comment Pass Is Not a Find-and-Replace

> Removing decoration from comments looks like four `sed` invocations. Every one of the four
> would have corrupted something, and two of them would have done it invisibly.

---

## 1. The same character is decoration in a docstring and content in an error toast

287 status emoji sat in this tree. 249 were decoration in comments. The other 33 were output:
Copilot error toasts, `Write-Host` console messages, JSX text, the `N FINDINGS` verdict label,
and a generated markdown heading in `auto_doc.py`.

The first idea was to split on the emoji-presentation selector, on the theory that a marker with
U+FE0F was user-facing and a bare one was a comment. That is wrong. Bare U+26A0 ships to users
from inside a `<span>` in `DrawingCanvas.tsx` and `GeometryInsightPanel.tsx`, from a string in
`renderEntities.ts`, and from the Copilot error toast in `copilotService.ts`.

The split has to be comment context against code context, which means locating prose per language:
`tokenize` plus `ast` for Python, so a docstring is found by being the first statement of a module
or function rather than by having triple quotes; a quote-aware scanner for TS/TSX, which also has
to know that `https://` is not a comment. JSX text is deliberately not a prose region, which is
what keeps a marker between tags.

## 2. The marker set is narrow, and measuring is what made it narrow

A scan for pictographic and symbol codepoints found 39 distinct characters. Most carry meaning:

- 119 U+2300 DIAMETER SIGN, the `⌀` this codebase standardised on in `utils/cadGlyphs.ts`
- 18 multiplication signs, as written in `6×⌀145`
- ~110 arrows, ordinary prose
- 15 GD&T symbols — CYLINDRICITY, FLATNESS, COUNTERBORE, TOTAL RUNOUT and the rest

`✓` is stricter still: `complianceChecklistSheet.ts` matches it with a regex, so it is parsed, not
drawn. `MARKERS` therefore holds only the coloured status badges, and
`test_cad_and_typographic_symbols_are_not_markers` fails if anyone widens it.

## 3. Bold spans wrap, so a line-by-line strip strands the closer

168 prose lines carried an odd number of `**` — not because the file was malformed, but because
the opener and the closer sat on different lines:

    The lesson generalises past the version bump: **a guard clause naming a
    concrete exception type is a dependency on that library's internals**, and

A per-line regex matches neither, or worse, matches one and leaves the other. Delimiters are
therefore collected across a whole comment block and paired in order, and a block whose count is
odd is left entirely alone and reported.

`**` is also not always emphasis. `docs/vault/**/*.md` is a glob inside a docstring table, `/**`
opens a JSDoc block, and this tree writes `2**14` and `2**16` in prose. Slash-adjacent handles the
first two. The third needed its own rule — alphanumeric on both sides is exponentiation — because
two exponentiations in one comment block make an even count and would have paired with each other.

## 4. The guard caught the regression and could not say so

Verifying the bold guard by reintroducing a bold span made it fail, with `TypeError`.
`Finding.__repr__` called `ord()` on a field holding one character for an emoji finding and two
for a bold one, and the assertion message — the part naming the file and telling you to run
`--fix` — never rendered.

The guard was correct and useless in the same breath. See
[[Gotcha - A Guard Test's Failure Path Had Never Run]]; this is the same shape, found the same way,
by insisting on watching a guard fail rather than watching it pass.

## 5. Some comments are read by machines

`tools/extraction_status.py` parses the `# vN:` block out of
`services/backend/domain/models/extracted_entity.py`, folding continuation lines into the note
above them and stopping at the first non-comment line. Rewording that block changes what the tool
reports, and no test guards it.

`cache_manager.py`, `mutator.py` and `learning/config.py` carry `# vN:` logs that constraint 2
requires, and one entry in `cache_manager.py` says explicitly that a gap in the log would read as
a mistake.

All four are excluded from compaction. The general rule: before rewriting a comment block, ask
whether anything parses it.

## 6. Comment density ranks the wrong files

The obvious metric — prose lines over non-blank lines — puts `cache_manager.py` first at 82%. That
file is 463 lines of the mandated cache-version log and must not be touched.

Measured across the tree, 26% of non-blank lines are prose, and the distribution is flat: the top
30 files hold only 30% of it. There is no high-value subset by density.

What does predict yield is whether the prose explains a dependency:

| file | prose | cut | what the comments were |
| :--- | ---: | ---: | :--- |
| `queryClient.ts` | 57 | 77% | what `staleTime` and `gcTime` mean |
| `main.tsx` | 38 | 52% | what `React.lazy` and Suspense are |
| `QueryErrorBoundary.tsx` | 82 | 45% | the TanStack error-reset lifecycle |
| `useManageItems.ts` | 170 | 28% | the onMutate / onError / onSettled lifecycle |
| `serialize.py` | 98 | 2% | why byte stability is required here |
| `encoder.py` | 29 | 6% | why the seam exists and what the predecessor faked |

A library's own documentation restated in a comment compacts hard and safely. A measurement or a
decision does not compact at all and must not be made to.

`useManageItems.ts` also showed that compacting a file's header is not compacting the file: the
header went easily, the measurement said 8%, and the same tutorial prose was still there one level
down. Re-measure per file; a spot check will not see it.

## The rule

A comment pass changes text that other things read — users, parsers, and the next engineer. Locate
prose properly rather than matching characters, pin the result with a guard that shares the
scanner, and watch the guard fail before believing it.

And when compacting: keep the decision and the consequence, drop the argument that led there. The
argument is what a vault note is for. This one.
