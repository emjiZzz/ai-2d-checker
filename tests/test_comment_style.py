"""
Enforce CLAUDE.md's "Writing style" rule that comments carry no decorative status emoji.

The rule was documentation for exactly as long as it took to write it, and documentation does not
survive contact with the next session: the marker style is copied from whatever the surrounding
code already does, so one reintroduced marker seeds the next hundred. This fails the build instead.

It shares `tools/comment_style.py` with the fixer rather than restating the rule, so the thing that
removes a marker and the thing that forbids one cannot disagree about where a comment ends.

The scanner distinguishes comment context from code context, which is the whole difficulty: the
same character is decoration in a docstring and content in an error toast. The non-vacuity tests
below pin both directions, because a scanner that finds nothing passes this file trivially.
"""

from __future__ import annotations

from pathlib import Path

from tools.comment_style import (
    OVERSIZED_BLOCK_LINES,
    oversized_blocks,
    MARKERS,
    bold_pairs,
    scan,
    scan_bold,
    scan_text,
    strip_bold,
    strip_text,
)

# Written as escapes so this file's own source carries no marker outside a string literal.
WARNING = "⚠"
RED_CIRCLE = "\U0001f534"
DIAMETER = "⌀"
MULTIPLY = "✕"
ARROW = "→"
CHECK = "✓"


def test_no_status_emoji_in_comments():
    """The guard. Run `python tools/comment_style.py --fix` if this fails."""
    findings = scan()
    assert findings == [], (
        f"{len(findings)} decorative status emoji in comments or docstrings. "
        "CLAUDE.md's Writing style section forbids them; "
        "run `services/backend/.venv/Scripts/python.exe tools/comment_style.py --fix`. "
        f"First few: {findings[:5]}"
    )


# --- non-vacuity: the scanner must actually see a marker in prose --------------------------------


def test_scanner_flags_a_marker_in_a_python_comment():
    src = f"x = 1  # {WARNING} do not do this\n"
    assert len(scan_text(Path("a.py"), src)) == 1


def test_scanner_flags_a_marker_in_a_python_docstring():
    src = f'def f():\n    """{RED_CIRCLE} Important."""\n    return 1\n'
    assert len(scan_text(Path("a.py"), src)) == 1


def test_scanner_flags_a_marker_in_a_ts_line_comment():
    src = f"const a = 1; // {WARNING} careful\n"
    assert len(scan_text(Path("a.ts"), src)) == 1


def test_scanner_flags_a_marker_in_a_ts_block_comment():
    src = f"/**\n * {WARNING} Careful.\n */\nconst a = 1;\n"
    assert len(scan_text(Path("a.ts"), src)) == 1


# --- non-vacuity: the scanner must NOT touch code ------------------------------------------------
#
# Every case here is a real site in this repo. They are the reason a blanket find-and-replace was
# rejected: it would have edited visible UI and a parsed badge string.


def test_scanner_ignores_a_marker_in_a_python_string_literal():
    src = f'msg = "{WARNING} An error occurred while generating the response."\n'
    assert scan_text(Path("a.py"), src) == []


def test_scanner_ignores_a_marker_in_a_ts_string_literal():
    src = f"const label = '{WARNING} Generators disagreed';\n"
    assert scan_text(Path("a.ts"), src) == []


def test_scanner_ignores_a_marker_in_a_template_literal():
    src = f"const label = `{WARNING} ${{count}} FINDINGS`;\n"
    assert scan_text(Path("a.ts"), src) == []


def test_scanner_ignores_a_marker_in_jsx_text():
    src = f'export const C = () => <span className="text-red">{WARNING}</span>;\n'
    assert scan_text(Path("a.tsx"), src) == []


def test_a_url_inside_a_string_is_not_a_comment():
    """`https://` contains `//`; treating it as a comment start would strip the rest of the line."""
    src = f'const u = "https://example.com/{WARNING}";\n'
    assert scan_text(Path("a.ts"), src) == []


# --- the marker set is deliberately narrow -------------------------------------------------------


def test_cad_and_typographic_symbols_are_not_markers():
    """These outnumber the markers in this source tree and every one of them carries meaning.

    U+2300 is the diameter sign this codebase standardised on in `utils/cadGlyphs.ts`; the
    multiplication sign appears in dimensions such as 6x{DIA}145; the arrow is ordinary prose; and
    `complianceChecklistSheet.ts` matches the check mark with a regex, so it is parsed, not drawn.
    Widening MARKERS to include any of them would corrupt drawing text.
    """
    for ch in (DIAMETER, MULTIPLY, ARROW, CHECK):
        assert ch not in MARKERS, f"U+{ord(ch):04X} carries meaning and must not be stripped"


def test_strip_removes_prose_markers_and_leaves_code_alone():
    src = (
        f"# {WARNING} A note.\n"
        f'ERROR = "{WARNING} Copilot is offline."\n'
        f'def f():\n    """{RED_CIRCLE} Docstring note."""\n'
    )
    out = strip_text(Path("a.py"), src)
    assert out.startswith("# A note.\n")
    assert f'ERROR = "{WARNING} Copilot is offline."' in out
    assert '"""Docstring note."""' in out


def test_strip_is_idempotent():
    src = f"# {WARNING} A note.\nx = 1\n"
    once = strip_text(Path("a.py"), src)
    assert strip_text(Path("a.py"), once) == once


# --- markdown bold -------------------------------------------------------------------------------
#
# Emphasis in a code comment is the second-loudest formatting tell after the emoji, and it carries
# nothing a sentence does not. The hazards are that a span wraps across lines and that a doubled
# asterisk is not always emphasis.

BOLD = "*" * 2


def test_no_markdown_bold_in_comments():
    """The guard. Run `python tools/comment_style.py --fix` if this fails."""
    findings = scan_bold()
    assert findings == [], (
        f"{len(findings)} markdown bold span(s) in comments or docstrings. "
        "CLAUDE.md's Writing style section forbids them; "
        "run `services/backend/.venv/Scripts/python.exe tools/comment_style.py --fix`. "
        f"First few: {findings[:5]}"
    )


def test_bold_is_found_in_a_python_comment():
    src = f"# {BOLD}Careful.{BOLD} Then the rest.\nx = 1\n"
    assert len(bold_pairs(Path("a.py"), src)) == 1


def test_bold_is_found_when_the_span_wraps_across_lines():
    """168 prose lines carried an odd asterisk count purely because spans wrap.

    A per-line strip would have removed the opener and left the closer stranded, so this is the
    case the block-level pairing exists for.
    """
    src = f"# The lesson is {BOLD}a guard clause naming a\n# concrete type is a dependency{BOLD}, and\nx = 1\n"
    assert len(bold_pairs(Path("a.py"), src)) == 1
    out = strip_bold(Path("a.py"), src)
    assert BOLD not in out


def test_exponentiation_in_prose_is_not_bold():
    """This tree writes 2**14 and 2**16 in prose. An even number of them in one comment block
    would pair with each other and be stripped, corrupting the text."""
    src = "# A dense 2**14 space costs more than a 2**16 sparse one.\nx = 1\n"
    assert bold_pairs(Path("a.py"), src) == []
    assert strip_bold(Path("a.py"), src) == src


def test_a_glob_is_not_bold():
    """`docs/vault/**/*.md` appears in a documented path inside a docstring."""
    src = f'"""Indexes docs/vault/{BOLD}/*.md by heading."""\nx = 1\n'
    assert bold_pairs(Path("a.py"), src) == []


def test_a_jsdoc_opener_is_not_bold():
    src = f"/{BOLD} Some doc.\n * More.\n */\nconst a = 1;\n"
    assert bold_pairs(Path("a.ts"), src) == []


def test_kwargs_in_a_comment_is_left_alone():
    """A single doubled asterisk makes the block's count odd, so the whole block is skipped."""
    src = f"# `{BOLD}kwargs` so the stub keeps matching as the signature grows.\nx = 1\n"
    assert bold_pairs(Path("a.py"), src) == []
    assert strip_bold(Path("a.py"), src) == src


def test_bold_in_a_string_literal_is_left_alone():
    src = f'LABEL = "{BOLD}bold{BOLD}"\n'
    assert bold_pairs(Path("a.py"), src) == []


def test_strip_bold_is_idempotent():
    src = f"# {BOLD}Careful.{BOLD}\nx = 1\n"
    once = strip_bold(Path("a.py"), src)
    assert strip_bold(Path("a.py"), once) == once


def test_finding_repr_renders_for_both_kinds():
    """The assertion messages above are the only caller of Finding.__repr__.

    It called `ord` on a field that holds two characters for a bold finding, so the bold guard
    raised TypeError and never printed the instruction to run --fix. A guard whose failure path
    has never run is not yet a guard.
    """
    emoji_src = f"# {WARNING} note\nx = 1\n"
    bold_src = f"# {BOLD}note{BOLD}\nx = 1\n"
    marker = scan_text(Path("a.py"), emoji_src)[0]
    assert "U+26A0" in repr(marker)

    from tools.comment_style import Finding
    o, _ = bold_pairs(Path("a.py"), bold_src)[0]
    assert "**" in repr(Finding(Path("a.py"), 1, o, "**", bold_src))


# --- oversized blocks ----------------------------------------------------------------------------


def test_no_new_comment_block_over_twenty_lines():
    """A ratchet, not a rule. It may fall; it may not rise.

    CLAUDE.md says an explanation over about five lines belongs in a vault note or a test name,
    linked rather than inlined. That was written for new prose and had never been applied to what
    was already here -- 63% of this tree's comment prose sits in blocks longer than five lines, and
    failing the suite on all of it would just get the rule deleted.

    So this pins the count of blocks over TWENTY lines, the size at which a comment is a document
    that happens to live in a source file. Adding one fails. Relocating one to the vault and
    leaving a linked summary lowers the number, and the baseline should be lowered with it.

    The four `# vN:` files are exempt: their blocks are mandated by constraint 2 or parsed by
    `tools/extraction_status.py`, so counting them would only invite someone to break one.

    A `#` run can be split by inserting a blank line, which would pass this without improving
    anything. Docstrings, which are the bulk of the problem, cannot -- a blank line inside one is
    still inside it. The gap is known and left, because a metric nobody can game is not worth the
    complexity here when the reviewer can see the diff.
    """
    baseline_blocks = 154
    baseline_lines = 4515

    blocks = oversized_blocks()
    lines = sum(n for _, _, n in blocks)
    worst = sorted(blocks, key=lambda b: -b[2])[:5]
    largest = ", ".join(f"{p.name}:{ln} ({n} lines)" for p, ln, n in worst)

    assert len(blocks) <= baseline_blocks, (
        f"{len(blocks)} comment blocks over {OVERSIZED_BLOCK_LINES} lines, baseline "
        f"{baseline_blocks}. Move the explanation to a vault note and leave a linked summary; "
        f"see CLAUDE.md's Writing style section. Largest: {largest}"
    )

    # Lines as well as count, because the count alone does not reward the work actually available.
    # Relocating `audit_orchestrator._retrieve_lessons_learned` took its block from 47 lines to 22
    # and moved the count by zero, 22 still being over the threshold. Most blocks here sit in that
    # range, so a count-only ratchet would score a 53% reduction as no progress.
    assert lines <= baseline_lines, (
        f"{lines} lines sit in oversized comment blocks, baseline {baseline_lines}. A block that "
        f"grew but stayed over {OVERSIZED_BLOCK_LINES} lines does not move the count. "
        f"Largest: {largest}"
    )

    assert len(blocks) >= baseline_blocks - 20 and lines >= baseline_lines - 400, (
        f"Down to {len(blocks)} blocks / {lines} lines against a baseline of {baseline_blocks} / "
        f"{baseline_lines}. That is good news: lower both baselines here so the ratchet holds the "
        "ground you gained."
    )
