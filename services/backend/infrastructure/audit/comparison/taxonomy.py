"""
Canonical sub-item taxonomy for the checklist UI (docs/checklist-taxonomy-grouping-
implementation-plan.md). `category` (one of the 6 top-level values already on
CanvasMarking/ComparisonCandidate) is a coarse grouping; `feature` is a finer one,
scoped within a category, used to group the checklist panel into named sub-sections
instead of one flat list per category.

This is the backend source of truth. It is hand-mirrored at
apps/desktop/src/utils/comparisonTaxonomy.ts — there is no runtime type-sharing
mechanism between the two languages in this repo (same precedent as
utils/comparisonStages.ts on the frontend side), so keeping the two in sync is a
discipline enforced by a cross-check test (Phase 8), not something automatic.
"""

from dataclasses import dataclass
from typing import Literal
import unicodedata

Category = Literal[
    "drawing_views",
    "notes_section",
    "bill_of_materials",
    "title_block",
    "isometric_view",
    "other_engineering_references",
]


@dataclass(frozen=True)
class FeatureItem:
    key: str
    label: str


# Appended by grouping code, not part of the arrays below — every category implicitly
# accepts findings that don't confidently match any of its named sub-items, rather than
# forcing a false-confidence guess or silently dropping them.
OTHER_FEATURE_KEY = "other"
OTHER_FEATURE_LABEL = "Other / Unclassified"

# Sub-items with no real extraction signal today (see docs/checklist-taxonomy-grouping-
# implementation-plan.md, decision 6) — the frontend renders these with a distinct
# "not yet supported" treatment instead of the normal "no changes detected" empty state,
# so they don't read as "checked and clean" when nothing was actually checked.
DEFERRED_FEATURES: set[str] = {"line_name"}

TAXONOMY: dict[Category, list[FeatureItem]] = {
    "drawing_views": [
        FeatureItem("origin", "Origin"),
        FeatureItem("alignment_of_views", "Alignment of Views"),
        FeatureItem("line_attributes", "Line Attributes"),
        FeatureItem("dimensions", "Dimensions"),
        FeatureItem("hole_properties", "Hole Properties"),
        FeatureItem("chamfer_radius", "Chamfer / Radius"),
        FeatureItem("machining_symbol", "Machining Symbol"),
        FeatureItem("welding_symbol", "Welding Symbol"),
        FeatureItem("geometric_tolerances", "Geometric Tolerances"),
        FeatureItem("additional_views", "Additional Views"),
        FeatureItem("text_attributes", "Text Attributes"),
    ],
    "notes_section": [
        FeatureItem("standard_notes", "Standard Notes"),
        FeatureItem("special_notes", "Special Notes"),
    ],
    "bill_of_materials": [
        FeatureItem("material_type", "Material Type"),
        FeatureItem("material_specification", "Material Specification"),
        FeatureItem("quantity", "Quantity"),
        FeatureItem("material_weight", "Material Weight"),
        FeatureItem("ballooning", "Ballooning"),
        FeatureItem("remarks", "Remarks"),
        FeatureItem("numbering_arrangement", "Numbering & Arrangement"),
    ],
    "title_block": [
        FeatureItem("machine_name", "Machine Name"),
        FeatureItem("line_name", "Line Name"),
        FeatureItem("scale", "Scale"),
        FeatureItem("creation_date", "Date of Creation"),
        FeatureItem("designed", "Designed"),
        FeatureItem("drawn", "Drawn"),
        FeatureItem("quantity", "Quantity"),
        FeatureItem("job_number", "Job Number"),
        FeatureItem("cross_reference_number", "Cross Reference Number"),
        FeatureItem("previous_drawing_number", "Previous Drawing Number"),
        FeatureItem("revision_code", "Revision Code"),
    ],
    "isometric_view": [
        FeatureItem("orientation", "Orientation"),
        FeatureItem("scale", "Scale"),
        FeatureItem("location", "Location"),
    ],
    "other_engineering_references": [
        FeatureItem("tree_view_properties", "Tree View Properties / Link"),
        FeatureItem("excel_additional_info", "Excel (Additional Information)"),
    ],
}


def _normalize_text(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "").strip().lower()
    return " ".join(t.split())


def normalize_feature(category: str, raw: str | None) -> str:
    """
    Matches a raw feature string (from Generator A's own key names, or Generator B's
    free-text guess) against the category's known taxonomy keys/labels. Falls back to
    OTHER_FEATURE_KEY on no confident match — never guesses, never raises. Matching is
    exact-after-normalization only (NFKC, lowercase, whitespace/underscore/hyphen
    collapse) against key or label; no fuzzy/similarity matching, so a near-miss from
    Gemini (e.g. a genuine synonym) intentionally falls to `other` rather than risking
    a wrong bucket silently pretending to be confident.
    """
    if not raw:
        return OTHER_FEATURE_KEY

    items = TAXONOMY.get(category)  # type: ignore[arg-type]
    if not items:
        return OTHER_FEATURE_KEY

    candidate = _normalize_text(raw).replace("-", "_").replace(" ", "_")
    candidate_loose = _normalize_text(raw)

    for item in items:
        if candidate == item.key:
            return item.key
        if candidate_loose == _normalize_text(item.label):
            return item.key
        if candidate_loose == _normalize_text(item.key.replace("_", " ")):
            return item.key

    return OTHER_FEATURE_KEY


def feature_label(category: str, feature_key: str | None) -> str:
    """Display label for a feature key within a category, falling back to the shared 'Other' label."""
    if feature_key:
        for item in TAXONOMY.get(category, []):  # type: ignore[arg-type]
            if item.key == feature_key:
                return item.label
    return OTHER_FEATURE_LABEL
