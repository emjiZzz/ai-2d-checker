"""
Find and remove decorative status emoji from comments and docstrings.

CLAUDE.md's "Writing style" section says comments carry no emoji markers. This is what makes
that true rather than aspirational: `tests/test_comment_style.py` imports `scan` and fails when
a marker appears in prose, so the rule is enforced instead of reviewed.

Run it to report, or with --fix to rewrite:

    services/backend/.venv/Scripts/python.exe tools/comment_style.py
    services/backend/.venv/Scripts/python.exe tools/comment_style.py --fix

## Only comment context, never code

The same character is decoration in a docstring and content in a string literal. A blanket
find-and-replace breaks visible UI: `renderEntities.ts` yields a marker inside
"Generators disagreed - needs manual review", `copilotService.ts` builds an error toast with one,
and two components render one inside a <span>. So prose regions are located per language --
`tokenize` plus `ast` for Python, a quote-aware scanner for TS/TSX -- and everything outside them
is left alone. JSX text is not a prose region, which is why a marker rendered between tags
survives.

The fixer and the test share `scan`, so what gets stripped and what gets guarded cannot disagree.
Anything the scanner cannot see stays visible in the reported count instead of being silently
skipped.

## What is NOT a marker

Measured before choosing: this source tree carries 119 U+2300 DIAMETER SIGN, 18 multiplication
signs, ~110 arrows and 15 GD&T symbols (CYLINDRICITY, FLATNESS, COUNTERBORE and the rest). Those
are CAD semantics or ordinary punctuation. `✓` is stricter still -- `complianceChecklistSheet.ts`
matches on it with a regex, so it is parsed, not drawn. MARKERS therefore holds only the coloured
status badges, which carry no meaning a sentence does not already carry.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Roots scanned by both the fixer and the guard test.
TRACKED_ROOTS = ("services/backend", "apps/desktop/src", "tools", "tests")
TRACKED_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".ps1", ".nsh"})
SKIP_PARTS = frozenset({".venv", "node_modules", "__pycache__", "dist", "target"})

# Decorative status badges only. See the module docstring for what is deliberately absent.
MARKERS = frozenset(
    "⚠"  # WARNING SIGN
    "\U0001f534"  # LARGE RED CIRCLE
    "✅"  # WHITE HEAVY CHECK MARK
    "⛔"  # NO ENTRY
    "\U0001f9ed"  # COMPASS
    "\U0001f9e0"  # BRAIN
    "\U0001f680"  # ROCKET
    "⏳"  # HOURGLASS WITH FLOWING SAND
    "\U0001f916"  # ROBOT FACE
    "\U0001f578"  # SPIDER WEB
    "\U0001f50d"  # LEFT-POINTING MAGNIFYING GLASS
    "\U0001f512"  # LOCK
    "\U0001f389"  # PARTY POPPER
)

VARIATION_SELECTOR = "️"

# A marker plus its emoji-presentation selector and the whitespace that separated it from the
# sentence. Applied only inside a prose span.
_MARKER_RUN = re.compile(
    f"[{''.join(MARKERS)}]{VARIATION_SELECTOR}?" + r"[ \t]*"
)


class Finding:
    __slots__ = ("path", "line", "col", "char", "text")

    def __init__(self, path: Path, line: int, col: int, char: str, text: str):
        self.path = path
        self.line = line
        self.col = col
        self.char = char
        self.text = text

    def __repr__(self) -> str:
        # `char` is one emoji for a marker finding and the two-character bold delimiter for a bold
        # one, so this cannot call `ord`. It did, and the only caller is the assertion message in
        # `tests/test_comment_style.py` -- which meant the guard raised TypeError instead of
        # printing the instruction to run --fix. The failure path is the whole product here, so it
        # is exercised by `test_finding_repr_renders_for_both_kinds`.
        rel = self.path.relative_to(REPO_ROOT) if self.path.is_absolute() else self.path
        label = f"U+{ord(self.char):04X}" if len(self.char) == 1 else repr(self.char)
        return f"{rel}:{self.line}: {label} in {self.text.strip()[:60]!r}"


# --- prose spans -------------------------------------------------------------------------------
#
# A span is (line_number, start_col, end_col) with a 1-indexed line and end_col exclusive.
# `_END` stands for "to the end of the line" so a caller need not know its length.

_END = 1 << 30


def _python_prose_spans(text: str) -> list[tuple[int, int, int]]:
    """Comment tokens plus module, class and function docstrings.

    Docstrings are located through `ast` rather than by matching triple quotes, because a string
    literal that merely happens to be triple-quoted is code, not prose.
    """
    spans: list[tuple[int, int, int]] = []

    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1], tok.end[1]))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return spans

    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr):
            continue
        value = first.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        end_line = value.end_lineno or value.lineno
        for line in range(value.lineno, end_line + 1):
            start = value.col_offset if line == value.lineno else 0
            end = value.end_col_offset if line == end_line else _END
            spans.append((line, start, end if end is not None else _END))

    return spans


def _ts_prose_spans(text: str) -> list[tuple[int, int, int]]:
    """`//` and `/* */` comments, tracked with enough quote awareness to skip `https://`.

    Deliberately not a parser. A construct it misreads -- an apostrophe in JSX text, say -- can
    only make it miss a comment, never invent one, so the failure mode is a marker left in place
    and counted, not a string literal rewritten.
    """
    spans: list[tuple[int, int, int]] = []
    in_block = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        n = len(line)
        start = 0 if in_block else None
        quote: str | None = None
        i = 0

        while i < n:
            if in_block:
                if line.startswith("*/", i):
                    spans.append((lineno, start or 0, i + 2))
                    in_block, start = False, None
                    i += 2
                    continue
                i += 1
                continue

            ch = line[i]
            if quote is not None:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
                i += 1
                continue

            if ch in "\"'`":
                quote = ch
                i += 1
                continue
            if line.startswith("//", i):
                spans.append((lineno, i, _END))
                break
            if line.startswith("/*", i):
                in_block, start = True, i
                i += 2
                continue
            i += 1

        if in_block and start is not None:
            spans.append((lineno, start, _END))

    return spans


def _line_comment_spans(text: str, marker: str) -> list[tuple[int, int, int]]:
    """Shell-family comments: `#` for PowerShell, `;` for NSIS, ignoring quoted occurrences."""
    spans: list[tuple[int, int, int]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        quote: str | None = None
        for i, ch in enumerate(line):
            if quote is not None:
                if ch == quote:
                    quote = None
                continue
            if ch in "\"'":
                quote = ch
                continue
            if ch == marker:
                spans.append((lineno, i, _END))
                break
    return spans


def prose_spans(path: Path, text: str) -> list[tuple[int, int, int]]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _python_prose_spans(text)
    if suffix in (".ts", ".tsx"):
        return _ts_prose_spans(text)
    if suffix == ".ps1":
        return _line_comment_spans(text, "#")
    if suffix == ".nsh":
        return _line_comment_spans(text, ";")
    return []


# --- scanning and fixing -----------------------------------------------------------------------


def scan_text(path: Path, text: str) -> list[Finding]:
    """Markers appearing inside a prose span. Everything else is code and is not reported."""
    by_line: dict[int, list[tuple[int, int]]] = {}
    for line, start, end in prose_spans(path, text):
        by_line.setdefault(line, []).append((start, end))

    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        ranges = by_line.get(lineno)
        if not ranges:
            continue
        for col, ch in enumerate(line):
            if ch in MARKERS and any(s <= col < e for s, e in ranges):
                findings.append(Finding(path, lineno, col, ch, line))
    return findings


def strip_text(path: Path, text: str) -> str:
    """Remove every marker inside a prose span, plus its selector and trailing spaces.

    Rewritten right-to-left within each line so earlier columns keep their offsets.
    """
    by_line: dict[int, list[tuple[int, int]]] = {}
    for line, start, end in prose_spans(path, text):
        by_line.setdefault(line, []).append((start, end))

    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    changed = False

    for idx, line in enumerate(lines):
        ranges = by_line.get(idx + 1)
        if not ranges:
            continue
        edits = [
            m for m in _MARKER_RUN.finditer(line)
            if any(s <= m.start() < e for s, e in ranges)
        ]
        if not edits:
            continue
        for m in reversed(edits):
            line = line[: m.start()] + line[m.end():]
        lines[idx] = line.rstrip() if not line.strip() else line
        changed = True

    return newline.join(lines) if changed else text


# --- markdown bold ------------------------------------------------------------------------------
#
# Comments in this tree emphasise with `...`, which is markdown formatting inside a code
# comment. Removing it is not a line-by-line job for two reasons found by measuring first:
#
# 1. A span wraps. 168 prose lines carry an odd number of `` because the opener and the closer
#    sit on different lines. Stripping per line would leave the orphan behind, which is worse than
#    leaving the pair alone.
# 2. `` is not always emphasis. `docs/vault/**/*.md` is a glob and `/**` opens a JSDoc block.
#    Both are recognised by an adjacent slash and skipped.
#
# Delimiters are therefore collected across a whole comment block, paired in order, and dropped
# only when the block's count is even. An odd block is left untouched and reported, so a construct
# the pairing does not understand stays visible instead of being half-edited.

_BOLD = "**"


def _line_offsets(text: str) -> list[int]:
    offsets, pos = [0], 0
    for ch in text:
        pos += 1
        if ch == "\n":
            offsets.append(pos)
    return offsets


def _prose_blocks(path: Path, text: str) -> list[tuple[int, int]]:
    """Absolute (start, end) offsets of maximal runs of prose on consecutive lines."""
    spans = prose_spans(path, text)
    if not spans:
        return []
    starts = _line_offsets(text)
    lines = text.split("\n")

    absolute: list[tuple[int, int, int]] = []
    for line, s, e in sorted(spans):
        if line - 1 >= len(lines) or line - 1 >= len(starts):
            continue
        base = starts[line - 1]
        end = min(e, len(lines[line - 1]))
        absolute.append((line, base + s, base + end))

    blocks: list[tuple[int, int]] = []
    cur_line, cur_start, cur_end = absolute[0]
    for line, s, e in absolute[1:]:
        if line - cur_line <= 1:
            cur_end = max(cur_end, e)
        else:
            blocks.append((cur_start, cur_end))
            cur_start, cur_end = s, e
        cur_line = line
    blocks.append((cur_start, cur_end))
    return blocks


def bold_pairs(path: Path, text: str) -> list[tuple[int, int]]:
    """Offsets of `**` delimiters that form a markdown bold pair inside one comment block."""
    pairs: list[tuple[int, int]] = []
    for block_start, block_end in _prose_blocks(path, text):
        marks: list[int] = []
        i = text.find(_BOLD, block_start, block_end)
        while i != -1:
            before = text[i - 1] if i else ""
            after = text[i + 2] if i + 2 < len(text) else ""
            # `/` on either side is a glob or a JSDoc opener. Alphanumeric on BOTH sides is
            # exponentiation -- this tree writes `2**14` and `2**16` in prose, and an even number
            # of those in one block would otherwise pair with each other and be stripped. A real
            # bold opener is never preceded by an alphanumeric, and a closer is never followed by
            # one.
            exponent = before.isalnum() and after.isalnum()
            if before != "/" and after != "/" and not exponent:
                marks.append(i)
            i = text.find(_BOLD, i + 2, block_end)

        if len(marks) % 2:
            continue
        for opener, closer in zip(marks[0::2], marks[1::2]):
            inner = text[opener + 2: closer]
            if not inner.strip() or inner[0].isspace() or inner[-1].isspace():
                continue
            pairs.append((opener, closer))
    return pairs


def strip_bold(path: Path, text: str) -> str:
    cuts: list[int] = []
    for opener, closer in bold_pairs(path, text):
        cuts.extend((opener, closer))
    if not cuts:
        return text
    out = text
    for pos in sorted(cuts, reverse=True):
        out = out[:pos] + out[pos + 2:]
    return out


def scan_bold(root: Path = REPO_ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_tracked_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not bold_pairs(path, text):
            continue
        starts = _line_offsets(text)
        for opener, _ in bold_pairs(path, text):
            line = max(i for i, off in enumerate(starts, 1) if off <= opener)
            findings.append(Finding(path, line, 0, _BOLD, text[opener: opener + 60]))
    return findings


# --- oversized blocks ----------------------------------------------------------------------------
#
# CLAUDE.md's Writing style section says an explanation needing more than about five lines belongs
# in a vault note or a test name, linked rather than inlined. That rule had never been applied to
# existing code: 63% of all prose in this tree sits in blocks longer than five lines.
#
# Retrofitting it is not something a tool can do, because deciding what a block's replacement
# sentence should say is the work. What a tool can do is stop the number growing, which is the
# half that compounds. `tests/test_comment_style.py` ratchets on the count below.
#
# The threshold is 20 rather than 5. Five is the target for new prose; twenty is the size at which
# a comment is unarguably a document that happens to live in a source file, and it leaves the 1,300
# blocks between the two alone rather than declaring most of the codebase in violation.

OVERSIZED_BLOCK_LINES = 20

# Blocks that cannot be moved, so counting them only invites someone to break a hard constraint.
# The `# vN:` logs are required by CLAUDE.md constraint 2, and `extracted_entity.py`'s is parsed by
# `tools/extraction_status.py`. `cache_manager.py`'s is 438 lines and was reported as the largest
# offender until this list existed.
EXEMPT_FROM_BLOCK_LIMIT = frozenset({
    "services/backend/domain/models/extracted_entity.py",
    "services/backend/infrastructure/audit/comparison/cache_manager.py",
    "services/backend/infrastructure/eval/mutator.py",
    "services/backend/infrastructure/learning/config.py",
})


def oversized_blocks(root: Path = REPO_ROOT, threshold: int = OVERSIZED_BLOCK_LINES):
    """Every movable comment block longer than `threshold` lines, as (path, first_line, count)."""
    found: list[tuple[Path, int, int]] = []
    for path in iter_tracked_files(root):
        if path.suffix.lower() not in (".py", ".ts", ".tsx"):
            continue
        if path.relative_to(root).as_posix() in EXEMPT_FROM_BLOCK_LIMIT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for start, end in _prose_blocks(path, text):
            size = text.count("\n", start, end) + 1
            if size > threshold:
                found.append((path, text.count("\n", 0, start) + 1, size))
    return found


def iter_tracked_files(root: Path = REPO_ROOT):
    for rel in TRACKED_ROOTS:
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in TRACKED_SUFFIXES:
                continue
            if SKIP_PARTS & set(path.parts):
                continue
            yield path


def scan(root: Path = REPO_ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_tracked_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_text(path, text))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--fix", action="store_true", help="rewrite the files in place")
    args = parser.parse_args(argv)

    emoji, bold = scan(), scan_bold()
    if not args.fix:
        by_file: dict[Path, int] = {}
        for f in emoji + bold:
            by_file[f.path] = by_file.get(f.path, 0) + 1
        for path, count in sorted(by_file.items(), key=lambda kv: -kv[1])[:20]:
            print(f"{count:4d}  {path.relative_to(REPO_ROOT)}")
        print(f"\n{len(emoji)} status emoji and {len(bold)} bold span(s) in comments, "
              f"across {len(by_file)} file(s).")
        print("Re-run with --fix to remove them.")
        return 1 if by_file else 0

    rewritten = 0
    for path in iter_tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = strip_bold(path, strip_text(path, text))
        if new != text:
            path.write_text(new, encoding="utf-8", newline="")
            rewritten += 1

    emoji, bold = scan(), scan_bold()
    print(f"Rewrote {rewritten} file(s); {len(emoji)} emoji and {len(bold)} bold span(s) remain.")
    for f in (emoji + bold)[:10]:
        print(f"  {f!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
