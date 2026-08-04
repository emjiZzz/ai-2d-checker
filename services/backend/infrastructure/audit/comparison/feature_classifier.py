"""
Heuristic feature classification for Generator A's free-form findings (docs/checklist-
taxonomy-grouping-implementation-plan.md, Phase 2, architecture decision 4).

Generator A's deterministic pipeline (SpatialDiffer-produced drawing_views/notes_section/
isometric_view findings) has no existing signal for which taxonomy sub-item a given text
belongs to — these rules provide REAL but PARTIAL signal: chamfer/radius, geometric
tolerances, hole properties, welding/machining symbols, and additional views can be
guessed from text patterns with reasonable confidence. `origin`, `alignment_of_views`,
`line_attributes`, and `text_attributes` have no reliable text-level signal at all and
are never assigned by these rules — Generator B (which reasons visually over the
rendered image) is the intended source for those four; Generator A's findings for them
stay `other` until/unless a future pass adds real geometric analysis.

Every function here degrades to `taxonomy.OTHER_FEATURE_KEY` on no confident match —
never guesses past what the pattern actually supports.
"""

import re
import unicodedata

from . import taxonomy


def _fold(text: str) -> str:
    """NFKC-fold text before pattern matching.

    Every pattern below is written in ASCII/halfwidth, but this corpus is Japanese CAD and
    writes callouts in FULLWIDTH: the chamfer that reads `C1` on one sheet is `Ｃ１` (U+FF23
    U+FF11) on the other. Without folding, `\\bC\\s*\\d+\\b` misses it and a real chamfer callout
    is classified `other`, landing the finding in "Other / Unclassified" instead of
    "Chamfer / Radius". The same gap hid fullwidth radii (`Ｒ５`), fullwidth plain dimensions
    (`１２０`) and fullwidth tolerances (`±０．０２`).

    `SpatialDiffer._normalize_text` already NFKC-folds, which is why the differ *pairs* a
    fullwidth and a halfwidth callout correctly — this classifier was the one place that did
    not, so the finding was matched but mislabelled.
    """
    return unicodedata.normalize("NFKC", text or "")

# GD&T feature control frame characters (partial — the common ones actually seen in
# CAD text extraction; a full GD&T symbol set is far larger than this needs to be).
_GDT_CHARS = "⊕⌖⌭⌰⌱⌲⌳⌴⌵⌯⏥⏤⏡"
# Dimensional fit/limit tolerance notation: "+0/-0.1" style (asymmetric — one side is
# often a bare integer with no decimal point at all), or a plain "±0.02".
_FIT_TOLERANCE_RE = re.compile(r'[+\-]\s*\d+(\.\d+)?\s*/\s*[+\-]\s*\d+(\.\d+)?|±\s*0?\.\d+')

# Chamfer (C1, C2, ...) / radius (R2, R0.5, ...) callouts.
_CHAMFER_RADIUS_RE = re.compile(r'\bC\s*\d+(\.\d+)?\b|\bR\s*\d+(\.\d+)?\b', re.IGNORECASE)

_HOLE_KEYWORDS = ("キリ", "ザグリ", "深サ", "深さ", "⌀", "Ø", "drill", "counterbore", "spot face")

# Fillet/bevel weld symbols vs. surface-finish (machining) marks — these were
# previously lumped together as one prompt item; Phase 3 splits them in Generator B's
# prompt too, so both generators use the same distinction.
_WELD_SYMBOL_CHARS = "△∨"
_MACHINING_SYMBOL_CHARS = "∇"

_ADDITIONAL_VIEW_KEYWORDS = (
    "section", "detail", "arrow view", "詳細", "断面", "矢視", "view a-a", "view b-b",
)

_DIMENSION_LIKE_RE = re.compile(r'^[\d.,\s±+\-/]+$')

_NOTES_SPECIAL_KEYWORDS = (
    "heat treat", "熱処理", "special", "特記", "コーティング", "coating", "plating", "メッキ",
)


def _contains_any_char(text: str, chars: str) -> bool:
    return any(ch in text for ch in chars)


def _contains_any_keyword(text: str, keywords: tuple) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def classify_drawing_view_feature(text_content: str, details: str = "") -> str:
    """Best-effort feature guess for a drawing_views finding from its own text — see module docstring for what this can and can't detect."""
    text_content = _fold(text_content)
    combined = _fold(f"{text_content or ''} {details or ''}")

    if _contains_any_char(combined, _GDT_CHARS) or _FIT_TOLERANCE_RE.search(combined):
        return "geometric_tolerances"
    if _contains_any_keyword(combined, _HOLE_KEYWORDS):
        return "hole_properties"
    if _CHAMFER_RADIUS_RE.search(combined):
        return "chamfer_radius"
    if _contains_any_char(combined, _WELD_SYMBOL_CHARS):
        return "welding_symbol"
    if _contains_any_char(combined, _MACHINING_SYMBOL_CHARS):
        return "machining_symbol"
    if _contains_any_keyword(combined, _ADDITIONAL_VIEW_KEYWORDS):
        return "additional_views"
    # A bare numeric-ish string (digits, decimal points, +/-, slashes) is the closest
    # generic signal for a plain dimension callout — deliberately narrow (fullmatch,
    # not search) so text merely containing a digit doesn't get claimed as a dimension.
    if text_content and _DIMENSION_LIKE_RE.fullmatch(text_content.strip()):
        return "dimensions"
    return taxonomy.OTHER_FEATURE_KEY


def classify_notes_feature(text_content: str, details: str = "") -> str:
    """
    notes_section only has two sub-items (standard_notes, special_notes). Unlike the
    other classifiers, a notes-zone finding is always some kind of note, so defaulting
    to `standard_notes` (rather than `other`) is the more useful fallback — `other`
    would just mean every unmatched note vanishes into an unhelpful catch-all bucket
    in a category that only has two real buckets to begin with.
    """
    combined = _fold(f"{text_content or ''} {details or ''}")
    if _contains_any_keyword(combined, _NOTES_SPECIAL_KEYWORDS):
        return "special_notes"
    return "standard_notes"


def classify_iso_feature(text_content: str, details: str = "") -> str:
    """
    isometric_view findings from SpatialDiffer are rare (isometric views often lack
    text labels — see full_ai_orchestrator.py's own prompt comment on this) and there
    is no reliable text signal to distinguish orientation/scale/location from each
    other. Always `other` rather than guess; kept as a function (not inlined) for
    interface consistency with the other two classifiers and so a future pass has an
    obvious place to add real signal.
    """
    return taxonomy.OTHER_FEATURE_KEY


def classify_title_ul_feature(display_key: str) -> str:
    """
    Maps an upper-left title-block header label (often bilingual, e.g.
    "Unit No. / ユニットNo.") to a taxonomy feature key. Used by
    orchestrator.py::extract_title_ul_kv, which discovers header/value pairs
    dynamically rather than from a fixed field list, so this classifier works off the
    discovered label text itself rather than a known field key.
    """
    key = _fold(display_key)
    lower = key.lower()
    if "unit" in lower or "part" in lower or "コード" in key or "機" in key:
        return "machine_name"
    if "q'ty" in lower or "qty" in lower or "quantity" in lower or "stock" in lower or "個数" in key or "棚" in key:
        return "quantity"
    return taxonomy.OTHER_FEATURE_KEY
