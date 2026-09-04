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

from tools.comment_style import MARKERS, scan, scan_text, strip_text

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
