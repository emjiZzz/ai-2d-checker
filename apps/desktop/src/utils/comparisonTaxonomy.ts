/**
 * Canonical sub-item taxonomy for the checklist UI (docs/checklist-taxonomy-grouping-
 * implementation-plan.md). Hand-mirrored from
 * services/backend/infrastructure/audit/comparison/taxonomy.py — there is no runtime
 * type-sharing mechanism between the two languages in this repo, so keeping these two
 * files in sync is a discipline, not something automatic (see the cross-check test in
 * Phase 8 of the plan doc). If you edit one, edit the other.
 *
 * `category` (one of the 6 top-level values already on CanvasMarking) is a coarse
 * grouping; `feature` is a finer one, scoped within a category, used to group the
 * checklist panel into named sub-sections instead of one flat list per category.
 */

export interface FeatureItem {
  key: string;
  label: string;
}

// Appended by grouping code, not part of the arrays below — every category implicitly
// accepts findings that don't confidently match any of its named sub-items.
export const OTHER_FEATURE_KEY = "other";
export const OTHER_FEATURE_LABEL = "Other / Unclassified";

// Sub-items with no real extraction signal today (see the plan doc, decision 6) —
// rendered with a distinct "not yet supported" treatment instead of the normal
// "no changes detected" empty state, so they don't read as "checked and clean" when
// nothing was actually checked.
export const DEFERRED_FEATURE_KEYS: ReadonlySet<string> = new Set(["line_name"]);

export const COMPARISON_TAXONOMY: Record<string, FeatureItem[]> = {
  drawing_views: [
    { key: "origin", label: "Origin" },
    { key: "alignment_of_views", label: "Alignment of Views" },
    { key: "line_attributes", label: "Line Attributes" },
    { key: "dimensions", label: "Dimensions" },
    { key: "hole_properties", label: "Hole Properties" },
    { key: "chamfer_radius", label: "Chamfer / Radius" },
    { key: "machining_symbol", label: "Machining Symbol" },
    { key: "welding_symbol", label: "Welding Symbol" },
    { key: "geometric_tolerances", label: "Geometric Tolerances" },
    { key: "additional_views", label: "Additional Views" },
    { key: "text_attributes", label: "Text Attributes" },
  ],
  notes_section: [
    { key: "standard_notes", label: "Standard Notes" },
    { key: "special_notes", label: "Special Notes" },
  ],
  bill_of_materials: [
    { key: "material_type", label: "Material Type" },
    { key: "material_specification", label: "Material Specification" },
    { key: "quantity", label: "Quantity" },
    { key: "material_weight", label: "Material Weight" },
    { key: "ballooning", label: "Ballooning" },
    { key: "remarks", label: "Remarks" },
    { key: "numbering_arrangement", label: "Numbering & Arrangement" },
  ],
  title_block: [
    { key: "machine_name", label: "Machine Name" },
    { key: "line_name", label: "Line Name" },
    { key: "scale", label: "Scale" },
    { key: "designed", label: "Designed" },
    { key: "drawn", label: "Drawn" },
    { key: "quantity", label: "Quantity" },
    { key: "job_number", label: "Job Number" },
    { key: "cross_reference_number", label: "Cross Reference Number" },
    { key: "previous_drawing_number", label: "Previous Drawing Number" },
    { key: "revision_code", label: "Revision Code" },
  ],
  isometric_view: [
    { key: "orientation", label: "Orientation" },
    { key: "scale", label: "Scale" },
    { key: "location", label: "Location" },
  ],
  other_engineering_references: [
    { key: "tree_view_properties", label: "Tree View Properties / Link" },
    { key: "excel_additional_info", label: "Excel (Additional Information)" },
  ],
};

/** Ordered sub-item list for a category, with the "Other" bucket always appended last. */
export function getTaxonomyWithOther(category: string): FeatureItem[] {
  const items = COMPARISON_TAXONOMY[category] ?? [];
  return [...items, { key: OTHER_FEATURE_KEY, label: OTHER_FEATURE_LABEL }];
}

/** Display label for a feature key within a category, falling back to the shared 'Other' label. */
export function featureLabel(category: string, featureKey: string | undefined | null): string {
  if (featureKey) {
    const item = (COMPARISON_TAXONOMY[category] ?? []).find(i => i.key === featureKey);
    if (item) return item.label;
  }
  return OTHER_FEATURE_LABEL;
}
