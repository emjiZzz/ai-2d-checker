import React, { useEffect, useState } from 'react';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import type { PickedEntity, StampTool } from '../../stores/workspace/types';
import { TOOL_SIDE } from '../../stores/workspace/slices/createManualCheckSlice';
import { MARKER_STYLES, type MarkerType } from './markerStyles';
import { CATEGORY_OPTIONS, findMarkingForEntity } from './manualCheckCategories';
import { COMPARISON_TAXONOMY } from '../../utils/comparisonTaxonomy';
import { cleanCadText } from '../../utils/cadGlyphs';
import { ChevronRight, ArrowLeft } from 'lucide-react';

/**
 * The menu that belongs to the SELECTED entity.
 *
 * ## Why it is not part of the right-click menu
 *
 * It was, until 2026-08-18. `CanvasContextMenu` is the canvas's own toolbox — annotation pins,
 * label visibility, marker filters — and the marking taxonomy was a guest in it, five coloured
 * rows below "Undo Delete". Two subjects sharing one gesture meant the engineer hunted for the
 * marking actions among the view controls, and the fix inside that menu (folding the categories
 * behind an "Add Checkmark" submenu) treated the symptom.
 *
 * Splitting them lets each gesture answer one question. Left-click: *what do I want to record
 * about this entity?* Right-click: *what do I want the canvas to do?*
 *
 * ⚠ **Selecting is still not recording.** This menu opens on selection but writes nothing; every
 * row here either opens the stamp modal or starts a pairing. That separation is the whole reason
 * left-click stopped stamping directly, and collapsing it back — a click that records — would
 * make an accidental click a ground-truth claim.
 *
 * ⚠ **MATCHED records both sheets when it can.** `selectionCounterpart` is published by the
 * OTHER canvas, which is where the pick index that resolved it lives; this component cannot see
 * that index. It is `null` when several candidates tied, so a pair is never guessed — and the
 * badge is then drawn on one sheet only, which is the honest rendering of a one-sided record.
 *
 * ⚠ **`NOT_A_FINDING` is deliberately absent** (owner's call, 2026-08-18). The status still
 * exists end to end — `MarkingStatus` accepts it, `STATUS_STYLE` renders it, and markings
 * recorded before this change still draw — it is simply not offered as something to record.
 * The cost is recorded in `ground_truth.py`: it was how a false positive got *attributed*
 * rather than merely counted, and on the reference sheet it was the only way to say "the engine
 * flagged this and it is fine". If that signal is wanted later, restoring it is one line here.
 *
 * ⚠ **Cancelling a pairing is deliberately NOT here.** It lives in the right-click menu because
 * that is the only surface that opens with nothing selected, which is exactly the state an
 * engineer is in when they change their mind about a pair half-made.
 */

/**
 * Highly specific bilingual labels for sub-items so engineers can match drawing cells directly.
 */
const SPECIFIC_ITEM_LABELS: Record<string, string> = {
  // Title Block
  unit_number: 'Unit No. (ユニットNo.)',
  part_number: 'Part No. (コードNo.)',
  quantity: 'Total Quantity (総製作個数 / T. Q\'ty)',
  stock_quantity: 'Stock Quantity (在庫棚入庫)',
  machine_name: 'Machine Name (機名 / ロールカセット)',
  line_name: 'Line Name (ライン名 / 押工板)',
  scale: 'Scale (尺度 / 1:1.5)',
  creation_date: 'Date of Creation (日付 / 04/12/22)',
  designed: 'Designed (設計)',
  drawn: 'Drawn (製図)',
  job_number: 'Job Number (工事番号 / 2589)',
  machine_unit_code: 'Machine Code (機器記号 / FSRS2)',
  previous_drawing_number: 'Drawing Number (図面番号 / M745221N01)',
  revision_code: 'Revision Code (改訂)',
  cross_reference_number: 'Cross Reference Number (参考図番)',

  // Bill of Materials
  material_type: 'Material Type (材質 / SS400)',
  material_specification: 'Material Specification (寸法・仕様 / 6×⌀145)',
  material_weight: 'Material Weight (重量 / 0.78 kg)',
  ballooning: 'Ballooning (照合番号 / バルーン)',
  remarks: 'Remarks (記事・備考)',
  numbering_arrangement: 'Numbering & Arrangement (照合順)',

  // Drawing Views
  dimensions: 'Dimensions (寸法 / ⌀145, 120)',
  hole_properties: 'Hole Properties (キリ穴・タップ / 6-9キリ)',
  chamfer_radius: 'Chamfer / Radius (面取り・R / C0.5, R5)',
  machining_symbol: 'Machining Symbol (仕上げ記号 / ▽)',
  geometric_tolerances: 'Geometric Tolerances (幾何公差)',
  welding_symbol: 'Welding Symbol (溶接記号)',
  line_attributes: 'Line Attributes (線種・線幅)',
  additional_views: 'Additional Views (詳細図・断面図 / A-A)',
};

const TITLE_BLOCK_PRIORITY: Record<string, number> = {
  unit_number: 1,
  part_number: 2,
  quantity: 3,
  stock_quantity: 4,
  machine_name: 5,
  line_name: 6,
  scale: 7,
  creation_date: 8,
  designed: 9,
  drawn: 10,
  job_number: 11,
  machine_unit_code: 12,
  previous_drawing_number: 13,
  revision_code: 14,
  cross_reference_number: 15,
};

/**
 * The colour and wording come from `MARKER_STYLES`, so the dot beside a menu row is the colour
 * the badge will actually be. They were separate literals and had drifted by two shades.
 */
const MANUAL_TOOLS: { tool: StampTool; marker: MarkerType }[] = [
  { tool: 'matched', marker: 'MATCHED' },
  { tool: 'mismatched', marker: 'MISMATCHED' },
  { tool: 'added', marker: 'ADDED' },
  { tool: 'removed', marker: 'REMOVED' },
];

interface SelectionMenuProps {
  x: number;
  y: number;
  canvasWidth?: number;
  canvasHeight?: number;
  theme: string;
  onClose: () => void;
}

export const SelectionMenu: React.FC<SelectionMenuProps> = ({
  x,
  y,
  canvasWidth,
  canvasHeight,
  theme,
  onClose,
}) => {
  const selectedEntities = useWorkspaceStore((s) => s.selectedEntities);
  const markings = useWorkspaceStore((s) => s.markings);
  const pendingPairRef = useWorkspaceStore((s) => s.pendingPairRef);
  const setPendingPairRef = useWorkspaceStore((s) => s.setPendingPairRef);
  const pendingPairTool = useWorkspaceStore((s) => s.pendingPairTool);
  const recordStamp = useWorkspaceStore((s) => s.recordStamp);
  const selectionCounterpart = useWorkspaceStore((s) => s.selectionCounterpart);

  // Escape dismisses, like any floating menu. Registered before the early return below so the
  // hook order stays fixed whether or not something is selected.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Set once a status is chosen but no category could be derived. Holds the stamp so the second
  // click has everything it needs.
  type Stamp = { tool: StampTool; ref: PickedEntity | null; rev: PickedEntity | null };
  const [awaitingCategory, setAwaitingCategory] = useState<Stamp | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  // A MATCHED with one side resolved, waiting for the engineer to pair it or accept it as-is.
  const [awaitingPairDecision, setAwaitingPairDecision] = useState<Stamp | null>(null);

  const picked = selectedEntities[0] ?? null;
  if (!picked) return null;

  /*
    Already marked? Then this menu does not open at all — hover the entity instead and the
    canvas shows the same detail card an engine finding gets, from the same renderer.

    That is the whole point: an AI room has no bespoke "already checked" panel, so a manual room
    must not grow one. It stops the double-marking (one entity, one judgement) without inventing
    a second way to display a record that already has a display. Removing one is done from the
    side panel, which is also where an engine finding is managed.
  */
  if (findMarkingForEntity(markings, picked)) return null;

  // Flip rather than clip. The menu is floated at the click, and a click near the right or
  // bottom edge of a pane is ordinary — the title block and the BOM both live there.
  const MENU_W = 210;
  const MENU_H = 150;
  const left = canvasWidth && x + MENU_W > canvasWidth ? Math.max(0, x - MENU_W) : x;
  const top = canvasHeight && y + MENU_H > canvasHeight ? Math.max(0, y - MENU_H) : y;

  // A pair completes only across the two sheets. A half waiting on the SAME side is the
  // engineer having picked the wrong entity, so the row below re-anchors it rather than
  // offering to pair something with itself — and says "start over" so the replacement is not
  // silent.
  const awaitingCounterpart = Boolean(pendingPairRef && pendingPairRef.side !== picked.side);
  // The stamp tools are lower-case; the style table is keyed by status. One conversion, here.
  const pendingTargetMarker = pendingPairTool.toUpperCase() as MarkerType;

  /**
   * The counterpart to record alongside a MATCHED, when one was resolved unambiguously.
   *
   * ADDED and REMOVED take only the clicked half by definition: an added entity has no reference
   * counterpart, and filling one would be a contradiction rather than a convenience.
   */
  const matchedCounterpart = (tool: StampTool) =>
    tool === 'matched' && selectionCounterpart?.side !== picked.side ? selectionCounterpart : null;

  /**
   * Record the stamp, or open the dialog when something still has to be asked.
   *
   * The dialog used to open for everything, and its required field was a category the sheet
   * already knew — the entity's zone IS its category. Derived stamps are written immediately and
   * marked `category_source: 'zone'`, which is what stops the corpus's attribution figure
   * becoming a tautology; see `categoryForZone`.
   *
   * It still opens for the two cases that earn it:
   *  - no category could be derived — a tolerance or shim table, or an entity in no measured
   *    zone. `null` from `categoryForZone` means ASK, never a default;
   *  - an unpaired MATCHED, where the engineer is about to claim a pair while recording half of
   *    one, and should be told before it lands rather than after.
   */
  /**
   * Record the stamp. Follows the explicit flow: Picked item -> Choose Status -> Pick what class.
   * This gives the engineer full manual control over the classification without relying on brittle heuristics.
   */
  const submit = (stamp: { tool: StampTool; ref: PickedEntity | null; rev: PickedEntity | null }) => {
    const unpairedMatched = stamp.tool === 'matched' && !(stamp.ref && stamp.rev);

    if (unpairedMatched) {
      setAwaitingPairDecision(stamp);
      return;
    }
    proceed(stamp);
  };

  /** Advance to the class selection step where the engineer explicitly selects the category. */
  const proceed = (stamp: { tool: StampTool; ref: PickedEntity | null; rev: PickedEntity | null }) => {
    setSelectedCategory(null);
    setAwaitingCategory(stamp);
  };

  const write = (
    stamp: { tool: StampTool; ref: PickedEntity | null; rev: PickedEntity | null },
    category: string,
    source: 'human' | 'zone',
    feature?: string | null,
  ) => {
    recordStamp(stamp, {
      category,
      categorySource: source,
      feature: feature ?? null,
      refText: stamp.ref?.text ?? '',
      revText: stamp.rev?.text ?? '',
      // Structurally always false/false/'' — nothing in the UI collects them. See
      // `CommitStampInput`; this is not a default that a caller elsewhere overrides.
      textWasEdited: false,
      isBulk: false,
      notes: '',
    });
    /*
      No `.catch` here, and that is the fix rather than an omission.

      This read `.catch(() => {})` until 2026-08-20, on the comment "the store logs and surfaces
      a failure". The store logged; nothing surfaced. So a failed POST — a stopped backend, a
      dropped connection, a 422 — produced no UI whatsoever: the menu closed, the entity stayed
      unmarked, and it was indistinguishable from a mis-click. On a 68-row sheet that is silent
      data loss in the one tool whose entire output is the records it keeps.

      `recordStamp` now settles rather than rejects, writing the reason to `markingError`, which
      `ManualMarkingList` renders beside the engineer's own work. There is nothing left to catch.
    */
  };

  const rowClass = `flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors ${
    theme === 'hc-light'
      ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
      : 'hover:bg-cyan-500/15 hover:text-cyan-400'
  }`;

  // ── the unpaired-MATCHED step ─────────────────────────────────────────────────────
  // MATCHED is a claim about a pair. Recording one with a single side is allowed — the engineer
  // can be right where the matcher is not — but it must be a decision rather than a side effect,
  // and the way to fix it has to be one click away or nobody takes it.
  if (awaitingPairDecision) {
    const missingSide = awaitingPairDecision.ref ? 'revision' : 'reference';
    return (
      <div
        className={`no-scrollbar absolute z-[10000] flex flex-col py-1 min-w-[230px] rounded-none border backdrop-blur-md shadow-xl select-none ${
          theme === 'hc-light'
            ? 'bg-white border-zinc-300 text-zinc-900 shadow-zinc-400/20'
            : 'bg-zinc-950/95 border-white/10 text-zinc-100 shadow-black/60'
        }`}
        style={{
          left,
          top,
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
        }}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-2.5 py-1.5 border-b border-white/10">
          <div className="text-[0.7rem] font-semibold" style={{ color: MARKER_STYLES.CHANGED.color }}>
            No counterpart found
          </div>
          <div className="text-[0.65rem] leading-snug opacity-70 mt-0.5">
            Nothing on the {missingSide} matches this value.
          </div>
        </div>
        <div
          className={rowClass}
          onClick={() => {
            setPendingPairRef(picked, 'matched');
            onClose();
          }}
        >
          <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: MARKER_STYLES.MATCHED.color }} />
          <span className="text-[0.72rem]">Pick counterpart on the {missingSide}…</span>
        </div>
        <div className={rowClass} onClick={() => proceed(awaitingPairDecision)}>
          <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: 'var(--text-muted)' }} />
          <span className="text-[0.72rem]">Record without a pair</span>
        </div>
      </div>
    );
  }

  // ── the category step ─────────────────────────────────────────────────────────────
  // Replaces the menu rather than nesting under it: at this point the status is already chosen
  // and the only open question is the category, so offering the statuses again would invite
  // changing an answer that has already been given.
  if (awaitingCategory) {
    const rawSubItems = selectedCategory ? (COMPARISON_TAXONOMY[selectedCategory] ?? []) : [];
    const subItems = selectedCategory === 'title_block'
      ? [...rawSubItems].sort((a, b) => (TITLE_BLOCK_PRIORITY[a.key] ?? 99) - (TITLE_BLOCK_PRIORITY[b.key] ?? 99))
      : rawSubItems;
    const selectedCatOption = CATEGORY_OPTIONS.find((c) => c.key === selectedCategory);

    return (
      <div
        className={`no-scrollbar absolute z-[10000] flex flex-col py-1 min-w-[270px] max-h-[380px] overflow-y-auto rounded-none border backdrop-blur-md shadow-xl select-none ${
          theme === 'hc-light'
            ? 'bg-white border-zinc-300 text-zinc-900 shadow-zinc-400/20'
            : 'bg-zinc-950/95 border-white/10 text-zinc-100 shadow-black/60'
        }`}
        style={{
          left,
          top,
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
        }}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className={`px-2.5 py-1.5 text-[0.62rem] font-mono truncate border-b flex items-center justify-between ${
            theme === 'hc-light' ? 'border-zinc-200 text-zinc-500' : 'border-white/10 text-zinc-500'
          }`}
        >
          {selectedCategory ? (
            <button
              className="flex items-center gap-1.5 hover:text-cyan-400 text-left transition-colors font-semibold"
              onClick={() => setSelectedCategory(null)}
            >
              <ArrowLeft className="w-3 h-3 text-cyan-400" />
              <span>{selectedCatOption?.label ?? selectedCategory} · CHOOSE ITEM</span>
            </button>
          ) : (
            <span>
              {MARKER_STYLES[awaitingCategory.tool.toUpperCase() as MarkerType]?.label ??
                awaitingCategory.tool}{' '}
              · CHOOSE CLASS
            </span>
          )}
        </div>

        {selectedCategory ? (
          <>
            <div
              className={`${rowClass} opacity-60 italic text-[0.68rem] border-b border-white/5`}
              onClick={() => {
                write(awaitingCategory, selectedCategory, 'human', null);
                setAwaitingCategory(null);
                setSelectedCategory(null);
                onClose();
              }}
            >
              <span>(General / Auto-classify)</span>
            </div>
            {subItems.map((item) => {
              const displayLabel = SPECIFIC_ITEM_LABELS[item.key] ?? item.label;
              return (
                <div
                  key={item.key}
                  className={rowClass}
                  onClick={() => {
                    write(awaitingCategory, selectedCategory, 'human', item.key);
                    setAwaitingCategory(null);
                    setSelectedCategory(null);
                    onClose();
                  }}
                >
                  <span className="text-[0.72rem] leading-snug">{displayLabel}</span>
                </div>
              );
            })}
          </>
        ) : (
          CATEGORY_OPTIONS.map((opt) => (
            <div
              key={opt.key}
              className={`${rowClass} justify-between`}
              onClick={() => {
                setSelectedCategory(opt.key);
              }}
            >
              <span className="text-[0.72rem]">{opt.label}</span>
              <ChevronRight className="w-3 h-3 opacity-40" />
            </div>
          ))
        )}
      </div>
    );
  }

  return (
    <div
      className={`no-scrollbar absolute z-[10000] flex flex-col py-1 min-w-[210px] rounded-none border backdrop-blur-md shadow-xl select-none ${
        theme === 'hc-light'
          ? 'bg-white border-zinc-300 text-zinc-900 shadow-zinc-400/20'
          : 'bg-zinc-950/95 border-white/10 text-zinc-100 shadow-black/60'
      }`}
      style={{
        left,
        top,
        scrollbarWidth: 'none',
        msOverflowStyle: 'none',
      }}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {/* What is about to be marked, and on which sheet. The side is not decoration: it decides
          which categories are even offered below. */}
      <div
        className={`px-2.5 py-1 text-[0.62rem] font-mono truncate border-b ${
          theme === 'hc-light' ? 'border-zinc-200 text-zinc-500' : 'border-white/10 text-zinc-500'
        }`}
        title={cleanCadText(picked.text) || picked.entityType}
      >
        {picked.side === 'ref' ? 'REFERENCE' : 'REVISION'} ·{' '}
        {selectedEntities.length > 1
          ? `${selectedEntities.length} entities selected`
          : cleanCadText(picked.text) || picked.entityType}
      </div>

      {MANUAL_TOOLS.filter(
        (t) => TOOL_SIDE[t.tool] === 'both' || TOOL_SIDE[t.tool] === picked.side,
      ).map((opt) => (
        <div
          key={opt.tool}
          className={rowClass}
          onClick={() => {
            // MATCHED is a claim about an entity that exists on BOTH sheets, so it records both
            // halves when the other one is known — the counterpart already outlined and labelled
            // on the far sheet as you read this menu. Nothing hidden is asserted: `null` when the
            // match was ambiguous, and the marking is then one-sided as before.
            //
            // ADDED and REMOVED take only the clicked half by definition: an added entity has no
            // reference counterpart to record, and filling one would be a contradiction.
            submit({
              tool: opt.tool,
              ref: picked.side === 'ref' ? picked : matchedCounterpart(opt.tool),
              rev: picked.side === 'rev' ? picked : matchedCounterpart(opt.tool),
            });
          }}
        >
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: MARKER_STYLES[opt.marker].color }}
          />
          <span className="text-[0.72rem]">{MARKER_STYLES[opt.marker].label}</span>
        </div>
      ))}

      {/*
        CHANGED is two clicks because it is two entities, and each must contribute its OWN
        coordinate. The old marker collapsed both sides onto one point, which is meaningless the
        moment a revision is re-traced.

        Startable from EITHER sheet since 2026-08-18. It used to begin on the reference only,
        which forced the engineer to notice the change from the side they were not reading —
        nothing about a CHANGED says which half you see first. The pair is assembled by each
        pick's own `side` rather than by the order they were clicked, so the halves cannot end
        up swapped.
      */}
      {awaitingCounterpart ? (
        // Completes as whatever the FIRST half declared — a pairing started from "Matched"
        // finishes as a MATCHED, not as a CHANGED. The verb travels with the pending half.
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors ${
            theme === 'hc-light'
              ? 'hover:bg-orange-600/10 hover:text-orange-700'
              : 'hover:bg-orange-500/15 hover:text-orange-400'
          }`}
          onClick={() =>
            submit({
              tool: pendingPairTool,
              ref: picked.side === 'ref' ? picked : pendingPairRef,
              rev: picked.side === 'rev' ? picked : pendingPairRef,
            })
          }
        >
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: MARKER_STYLES[pendingTargetMarker].color }}
          />
          <span className="text-[0.72rem] truncate">
            {MARKER_STYLES[pendingTargetMarker].label} with “
            {pendingPairRef!.text || pendingPairRef!.entityType}”
          </span>
        </div>
      ) : (
        <>
          <div
            className={rowClass}
            onClick={() => {
              setPendingPairRef(picked, 'changed');
              onClose();
            }}
          >
            <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: MARKER_STYLES.CHANGED.color }} />
            <span className="text-[0.72rem]">
              {pendingPairRef ? 'Changed — start over from here…' : 'Changed — pick counterpart…'}
            </span>
          </div>

          {/*
            The manual route for MATCHED, offered only when the automatic one had no answer.

            `selectionCounterpart` is null when the matcher found nothing or could not choose
            between several — and "nothing" includes the case that matters most here: two values
            that genuinely DIFFER on the two sheets and are nonetheless the same item. On
            `M745204N01` the reference reads `2 ロール：4 (2x2台)` against the revision's
            `2ロール：4（2×6台）`; no normalisation should equate those, and an engineer looking
            at both sheets still can. Without this row that judgement had nowhere to go.

            Hidden when the counterpart WAS resolved, because the plain "Matched" row above
            already records both halves and a second way to do the same thing is how two
            gestures start meaning different things.
          */}
          {!selectionCounterpart && (
            <div
              className={rowClass}
              onClick={() => {
                setPendingPairRef(picked, 'matched');
                onClose();
              }}
            >
              <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: MARKER_STYLES.MATCHED.color }} />
              <span className="text-[0.72rem]">Matched — pick counterpart…</span>
            </div>
          )}
        </>
      )}
    </div>
  );
};
