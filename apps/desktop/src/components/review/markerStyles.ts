/**
 * One table of what a finding LOOKS like, whatever produced it.
 *
 * ## Why this exists
 *
 * There were two, and they disagreed about the same words. The engine's markers coloured
 * `MATCHED` `#39ff14` and `ADDED` `#00ffff`; manual markings and the menus used `#10b981` and
 * `#3b82f6`. Nothing was broken — both rendered fine — so the drift was invisible until an
 * engineer looked at one drawing carrying both kinds and asked why a checkmark recorded by hand
 * did not look like a checkmark found by the engine.
 *
 * That is the shape this codebase keeps paying for: two copies of one rule, both working, slowly
 * disagreeing. A status is a statement about a drawing; what colour it is drawn in must not
 * depend on which subsystem noticed it.
 *
 * ## The vocabulary is the union of both sources
 *
 * `MISMATCHED` and `CONFLICT` only ever come from the engine; `REMOVED` and `NOT_A_FINDING` only
 * from a human. Keeping them in ONE table rather than two is the point — a marker filter that
 * knows five of the seven silently hides the other two, which is how a manual REMOVED would
 * vanish from a sheet while its row still sat in the side panel.
 */

export type MarkerType =
  | 'MISMATCHED'
  | 'CHANGED'
  | 'ADDED'
  | 'MATCHED'
  | 'CONFLICT'
  | 'REMOVED'
  | 'NOT_A_FINDING';

export interface MarkerStyle {
  /**
   * ON THE CANVAS. High-chroma on purpose — it is drawn over a dark CAD sheet among green and
   * yellow geometry, and a muted colour disappears into it.
   */
  color: string;
  /** Drawn inside the bullet. */
  glyph: string;
  /** Shown on the detail card and in the filter menu. */
  label: string;
  /**
   * IN A PANEL, dark theme. Not the same value as `color`, and deliberately so: `#39ff14` on a
   * card is a strain to read and unusable on white. Same status, same table, two contexts.
   */
  ui: string;
  /** IN A PANEL, light theme. Darkened for contrast against a white card. */
  uiLight: string;
}

export const MARKER_STYLES: Record<MarkerType, MarkerStyle> = {
  MISMATCHED: { color: '#ff2850', ui: '#ef4444', uiLight: '#b91c1c', glyph: '!', label: 'Mismatched / Wrong' },
  CHANGED: { color: '#ff9600', ui: '#f97316', uiLight: '#c2410c', glyph: '⇄', label: 'Changed' },
  ADDED: { color: '#00ffff', ui: '#3b82f6', uiLight: '#1d4ed8', glyph: '+', label: 'Added' },
  MATCHED: { color: '#39ff14', ui: '#10b981', uiLight: '#047857', glyph: '✓', label: 'Matched' },
  CONFLICT: { color: '#c084fc', ui: '#a855f7', uiLight: '#7e22ce', glyph: '?', label: 'Conflict' },
  REMOVED: { color: '#ff2850', ui: '#ef4444', uiLight: '#b91c1c', glyph: '−', label: 'Removed' },
  NOT_A_FINDING: { color: '#a1a1aa', ui: '#a1a1aa', uiLight: '#71717a', glyph: '×', label: 'Not a finding' },
};

/**
 * A status's colour in a PANEL, and the translucent wash behind it.
 *
 * Folded here on 2026-08-18 from `ChecklistPanel`, which carried the palette three more times —
 * two hand-written ternary chains in the finding card and a third set in the summary chips. They
 * had already drifted: CHANGED was `#f97316` on a card and `#f59e0b` in the chip beside it, in
 * the same panel, for the same finding. Nothing was broken, which is why it survived.
 *
 * The hex-alpha suffix is the idiom `ChecklistSection` and `FindingCard` already use for their
 * pills — one less colour format to keep in step.
 */
export const markerUi = (type: string, isLight: boolean) => {
  const style = markerStyle(type);
  const color = isLight ? style.uiLight : style.ui;
  return { color, background: `${color}${isLight ? '1f' : '24'}` };
};

export const markerStyle = (type: string): MarkerStyle =>
  MARKER_STYLES[type as MarkerType] ?? MARKER_STYLES.MISMATCHED;

/**
 * A marker's ink for the surface it is being painted on.
 *
 * Three surfaces, one table. `color` is tuned for the dark CAD canvas and is high-chroma on
 * purpose; `ui` / `uiLight` exist because — as the table above already says — `#39ff14` is
 * "unusable on white".
 *
 * **The PDF export paints on white.** It had been using `color`, so every checkmark on the
 * printed sheet was neon green over near-black linework: three times the weight of the drawing it
 * was annotating, and the first thing the eye landed on. That is the exact problem `uiLight` was
 * introduced to solve, so it is the same answer rather than a fourth column in the table.
 */
export const markerInkFor = (type: string, surface: 'canvas' | 'print'): string =>
  surface === 'print' ? markerStyle(type).uiLight : markerStyle(type).color;

/**
 * The engine's pen vocabulary, which predates this table and is what a stored violation carries.
 *
 * Kept as a translation INTO `MarkerType` rather than alongside it: a cached audit payload holds
 * `pen_type`, so the mapping has to survive, but nothing new should be written in these terms.
 * `resolved_green` and `ai_green` both mean matched — the first is an engine finding a human
 * later resolved, and the distinction is carried by the violation's own fields, not its colour.
 */
export const PEN_TYPE_TO_MARKER: Record<string, MarkerType> = {
  // REMOVED, not MISMATCHED. `markerGenerator` assigns this pen on exactly one condition —
  // `if (marking.status === "REMOVED") penType = "ai_red"` — so the engine's own meaning is not
  // in doubt. The canvas called it MISMATCHED for as long as it had a label, which put the wrong
  // word on every removal's detail card and filed them under a filter nobody would think to use.
  ai_red: 'REMOVED',
  ai_orange: 'CHANGED',
  checker_blue: 'ADDED',
  ai_green: 'MATCHED',
  resolved_green: 'MATCHED',
  ai_conflict: 'CONFLICT',
};

/**
 * Spellings of a status that are not `MarkerType`, folded onto one that is.
 *
 * The engine says `MISSING` where the taxonomy says `REMOVED` — `ChecklistPanel` has always
 * tested `=== "REMOVED" || === "MISSING"` and that is where this list comes from. An unmapped
 * spelling is not cosmetic: `markerTypeOf` returns null for it and the marker is not drawn at
 * all, so the finding exists in the panel and nowhere on the sheet.
 */
const STATUS_ALIASES: Record<string, MarkerType> = {
  MISSING: 'REMOVED',
  MISMATCH: 'MISMATCHED',
  NOT_A_FINDING: 'NOT_A_FINDING',
};

/**
 * What kind of marker this is, from whichever vocabulary it carries.
 *
 * Order matters. `status` is the engine's own verdict and a manual marking's only vocabulary, so
 * it wins; `pen_type` is the older rendering hint and answers for cached payloads that predate
 * `status` being passed through. `null` means "do not draw", which is deliberately loud —
 * silently drawing an unknown as MISMATCHED would put a red mark on something nobody flagged.
 */
export function markerTypeOf(v: {
  status?: string | null;
  pen_type?: string | null;
}): MarkerType | null {
  const raw = String(v?.status ?? '').toUpperCase().trim();
  if (raw) {
    if (raw in MARKER_STYLES) return raw as MarkerType;
    if (raw in STATUS_ALIASES) return STATUS_ALIASES[raw];
  }
  return PEN_TYPE_TO_MARKER[v?.pen_type ?? ''] ?? null;
}

/**
 * Which sheet a marker type belongs on, or `null` when it belongs on both.
 *
 * **This is the same rule as `TOOL_SIDE` in `createManualCheckSlice`, one layer down.** That
 * one decides what the engineer may RECORD; this one decides what is DRAWN. They must agree:
 * a status recordable on the reference but undrawable there is a marking that vanishes the
 * moment it is made, which reads as a failed write.
 *
 * `MISMATCHED` and `REMOVED` describe something present on the reference and absent from the
 * revision, so they anchor on the reference. `ADDED` is the mirror. Everything else exists on
 * both sheets and draws wherever it has a coordinate.
 */
export const MARKER_SIDE: Record<MarkerType, 'ref' | 'rev' | null> = {
  MISMATCHED: null,
  REMOVED: 'ref',
  ADDED: 'rev',
  CHANGED: null,
  MATCHED: null,
  CONFLICT: null,
  NOT_A_FINDING: null,
};

/**
 * A recorded manual marking, in the shape the marker renderer already understands.
 *
 * Adapting rather than reimplementing: `renderViolationReticles` already solves bullet drawing,
 * the detail card, label collision avoidance, level-of-detail culling and hover — and solving
 * any of that a second time is how the two visual languages appeared in the first place.
 *
 * `status` is passed through as the marker type directly. The engine's violations reach the same
 * renderer through `pen_type`, which has no `REMOVED`; routing a manual REMOVED through
 * `ai_red` would have labelled it "MISMATCHED" on its own card.
 */
export function markingsToMarkers(markings: any[]): any[] {
  const out: any[] = [];
  for (const m of markings ?? []) {
    // Skipped, not thrown on. This runs inside a render pass, where one bad row would take the
    // whole canvas rather than one badge — and the rows come off the wire.
    if (!m) continue;
    // A retraction is not a deletion — the row stays as the audit trail of who asserted what —
    // but it must not be drawn, or the sheet shows a judgement its author withdrew.
    if (m.retracted_at) continue;
    out.push({
      // Namespaced so a marking id can never collide with a violation id in
      // `markerPositionsRef`, which is keyed by id and shared across both.
      id: `marking:${m.id}`,
      status: String(m.status ?? 'MATCHED'),
      category: m.category ?? '',
      description: m.rev_text ?? '',
      original_value: m.ref_text ?? '',
      coordinates: m.rev_coordinates ?? null,
      ref_coordinates: m.ref_coordinates ?? null,
      // Drawn as a ring around the bullet: one editorial act standing for several entities must
      // not read as a single stamp, or the corpus's bulk counts cannot be reconciled by eye.
      is_bulk: Boolean(m.is_bulk),
    });
  }
  return out;
}
