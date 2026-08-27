import { MARKER_STYLES, markerStyle } from './markerStyles';
import { ChecklistSection } from './ChecklistSection';
import { ComparisonGridStyles, ComparisonValues, FindingCard } from './FindingCard';
import { useThemeStore } from '../../stores/themeStore';
import React, { useCallback, useMemo, useState } from 'react';
import { Trash2, CheckCircle2, ClipboardCheck, Download, RotateCcw } from 'lucide-react';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useRoomStore } from '../../stores/roomStore';
import { useIsManualCheckRoom } from '../../hooks/useManualCheckRoom';
import { useComplianceReportExport } from '../../hooks/useComplianceReportExport';
import { CATEGORY_KEYS, categoryLabel } from './manualCheckCategories';
import { ExportStatusNote } from './ExportStatusNote';
import { ExportOverlay } from './ExportOverlay';
import { StaleExtractionBadge } from './StaleExtractionBadge';

/**
 * The live marking list — the whole left panel in a manual-check room.
 *
 * Renders inside the existing panel rather than as a new flexlayout tab, so the saved layout key
 * does not have to be bumped and nobody's arrangement resets.
 *
 * All **six** categories are shown, including the two the AI checklist omits: `isometric_view`
 * is one of the corpus's four recorded false-negative classes, and a category with no heading is
 * one an engineer does not think to look for.
 *
 * Colours are CSS variables so the panel follows `data-theme` with no branching. It previously
 * read `theme` off `reviewStore`, which does not have it — the selector returned `undefined` and
 * the dark styling was applied unconditionally.
 */

// Shared with the canvas badges rather than restated: a list dot and its badge disagreeing
// about what ADDED looks like is small, silent and exactly the drift this codebase keeps paying
// for. One map, imported by both.

export const ManualMarkingList: React.FC = () => {
  const isManualCheckRoom = useIsManualCheckRoom();
  const theme = useThemeStore((s) => s.theme);

  const markings = useWorkspaceStore((s) => s.markings);
  const annotations = useWorkspaceStore((s) => s.annotations);
  // Subscribed, not read through `getState()` like `retryOpen` does: the stale badge below has
  // to re-render when the pair changes, and `extraction_is_stale` arrives with the drawing.
  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const newDrawing = useWorkspaceStore((s) => s.newDrawing);
  const deleteAnnotationById = useWorkspaceStore((s) => s.deleteAnnotationById);
  const manualSessionId = useWorkspaceStore((s) => s.manualSessionId);
  const manualSessionError = useWorkspaceStore((s) => s.manualSessionError);
  const startManualSession = useWorkspaceStore((s) => s.startManualSession);

  const { exportToPDF, isExporting, exportPhase, exportStatus, revealExport } =
    useComplianceReportExport();

  // Retry re-runs the open with the SAME identity the effect would have used. It does not clear
  // the error first: if the second attempt fails too, the message must not flicker away and
  // leave the empty invitation behind, which is the very confusion this block exists to end.
  const retryOpen = useCallback(() => {
    const room = useRoomStore.getState().activeRoom;
    const ws = useWorkspaceStore.getState();
    if (!room?.id || !ws.oldDrawing?.id || !ws.newDrawing?.id) return;
    startManualSession(String(room.id), String(ws.oldDrawing.id), String(ws.newDrawing.id));
  }, [startManualSession]);
  const pendingPairRef = useWorkspaceStore((s) => s.pendingPairRef);
  const pendingPairTool = useWorkspaceStore((s) => s.pendingPairTool);
  const retractManualMarking = useWorkspaceStore((s) => s.retractManualMarking);
  const submitManualSession = useWorkspaceStore((s) => s.submitManualSession);
  const reopenManualSession = useWorkspaceStore((s) => s.reopenManualSession);
  const markingError = useWorkspaceStore((s) => s.markingError);
  const clearMarkingError = useWorkspaceStore((s) => s.clearMarkingError);

  const [submitting, setSubmitting] = useState(false);
  // Open by default: this panel is short and the engineer is reading their own work, not
  // triaging someone else's. Collapsed-by-default would hide the thing they came here for.
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const manualSessionStatus = useWorkspaceStore((s) => s.manualSessionStatus);
  const isSubmitted = submitted || manualSessionStatus === 'submitted' || manualSessionStatus === 'completed';

  const grouped = useMemo(() => {
    const map: Record<string, typeof markings> = {};
    for (const key of CATEGORY_KEYS) map[key] = [];
    for (const m of markings) (map[m.category] ??= []).push(m);
    return map;
  }, [markings]);

  if (!isManualCheckRoom) return null;

  /*
    `submitted` is set from the SERVER's answer, never unconditionally.

    It read `await submitManualSession(); setSubmitted(true)` until 2026-08-20, and the store
    swallowed its own failure — so a submit that never reached the database rendered "Check
    submitted" and the engineer walked away from a session still marked `in_progress`. The store
    now returns whether the server confirmed it, and writes the reason to `markingError` when it
    did not.
  */
  const submit = async () => {
    setSubmitting(true);
    const ok = await submitManualSession();
    setSubmitting(false);
    if (ok) setSubmitted(true);
  };

  const totalCount = markings.length + annotations.length;
  const canSubmit = Boolean(manualSessionId) && totalCount > 0 && !submitting && !isSubmitted;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div
        style={{
          padding: '10px 12px',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <div
          style={{
            width: 22,
            height: 22,
            borderRadius: 4,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(16,185,129,0.12)',
            border: '1px solid rgba(16,185,129,0.28)',
            flexShrink: 0,
          }}
        >
          <ClipboardCheck size={13} color="#10b981" />
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--text-primary)',
            }}
          >
            Ground Truth Markings
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>
            {manualSessionId
              ? `${totalCount} item${totalCount === 1 ? '' : 's'} recorded`
              : 'Opening session…'}
          </div>
        </div>
      </div>

      {/*
        Stale-extraction warning for the pair being marked.

        ⚠ **This is the only place it can appear in a prototype build.** `StaleExtractionBadge`
        previously lived solely in `TwoDRightPanel`, which renders only when
        `isPhysicalComparisonEnabled || aiScanProgress === "completed" || isStandardsAuditCompleted`
        — and the first of those is set in exactly one place, after the comparison engine runs
        (`usePhysicalComparison`). Prototype mode forces every room to `manual_check` so the engine
        never runs, the flag is permanently false, the panel is never created, and the badge was
        structurally unreachable in the build handed to engineers for data gathering.

        That is the worst place to lose it: `render_paths`, dimension text anchors, leader
        hooklines, arrowheads, MTEXT rotation and the angular-degree conversion are computed at
        EXTRACTION time, so a stale sheet renders wrong while looking perfectly ordinary. At the
        time this was added, `tools/extraction_status.py` reported 38 of 65 stored drawings stale,
        20 of them at v2 — five versions behind. An engineer marking one of those produces corpus
        ground truth taken from arrowheads that are missing and a dimension reading 1.05 where the
        paper says 60°, and nothing anywhere would flag it.

        Renders nothing when both drawings are current — the badge's own no-op contract, which is
        what makes it safe in an always-visible panel.
      */}
      {(oldDrawing?.extraction_is_stale || newDrawing?.extraction_is_stale) && (
        <div
          style={{
            padding: '8px 12px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}
        >
          <StaleExtractionBadge drawing={oldDrawing} label="Reference" />
          <StaleExtractionBadge drawing={newDrawing} label="Revision" />
        </div>
      )}

      {/* A pairing in flight, surfaced here as well as in the menu. Without it the first half of
          a CHANGED pair is invisible state, and a click that appears to do nothing is how a user
          concludes the tool is broken. */}
      {pendingPairRef && (
        <div
          style={{
            padding: '7px 12px',
            fontSize: 11,
            lineHeight: 1.45,
            color: MARKER_STYLES.CHANGED.color,
            background: 'rgba(249,115,22,0.1)',
            borderBottom: '1px solid var(--border-color)',
          }}
        >
          Pairing “{pendingPairRef.text || pendingPairRef.entityType}” as{' '}
          {pendingPairTool.replace(/_/g, ' ')} — select its counterpart on the{' '}
          {pendingPairRef.side === 'ref' ? 'revision' : 'reference'}.
        </div>
      )}

      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '8px 8px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        {/*
          A failed load and an empty session used to look identical — both showed the invitation
          below, so "the server did not answer" read as "you have recorded nothing". That is the
          worst possible confusion for this panel: it is the only place an engineer can see their
          own work, and it says the work is not there.
        */}
        {manualSessionError && (
          <div
            style={{
              fontSize: 11,
              lineHeight: 1.6,
              padding: '8px',
              marginBottom: 8,
              color: MARKER_STYLES.MISMATCHED.color,
              background: 'rgba(255,40,80,0.08)',
              border: `1px solid ${MARKER_STYLES.MISMATCHED.color}55`,
            }}
          >
            <div style={{ fontWeight: 600 }}>Could not open this check.</div>
            <div style={{ color: 'var(--text-muted)', margin: '4px 0 8px' }}>
              Your recorded markings are on the server, not lost — this pane just could not read
              them. {manualSessionError}
            </div>
            <button
              type="button"
              onClick={retryOpen}
              style={{
                fontSize: 11,
                padding: '3px 10px',
                cursor: 'pointer',
                color: 'var(--text-primary)',
                background: 'transparent',
                border: '1px solid var(--border-color)',
              }}
            >
              Retry
            </button>
          </div>
        )}

        {/*
          A WRITE that failed, as opposed to the open failure above. Separate blocks because they
          say opposite things about the engineer's work: the open error says "your markings are
          safe, this pane just could not read them", and this one says "what you just did was not
          recorded". Collapsing the two into one banner would make the reassuring wording appear
          over a lost stamp.

          Dismissible rather than auto-clearing on a timer: the next successful write clears it,
          and until then it is the only evidence that something did not land.
        */}
        {markingError && (
          <div
            style={{
              fontSize: 11,
              lineHeight: 1.6,
              padding: '8px',
              marginBottom: 8,
              color: MARKER_STYLES.MISMATCHED.color,
              background: 'rgba(255,40,80,0.08)',
              border: `1px solid ${MARKER_STYLES.MISMATCHED.color}55`,
            }}
          >
            <div style={{ fontWeight: 600 }}>Not recorded.</div>
            <div style={{ color: 'var(--text-muted)', margin: '4px 0 8px' }}>{markingError}</div>
            <button
              type="button"
              onClick={clearMarkingError}
              style={{
                fontSize: 11,
                padding: '3px 10px',
                cursor: 'pointer',
                color: 'var(--text-primary)',
                background: 'transparent',
                border: '1px solid var(--border-color)',
              }}
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Once per panel, not per card — one <style> element per row is what the checklist
            learned to avoid. */}
        <ComparisonGridStyles />

        {markings.length === 0 && annotations.length === 0 && !manualSessionError && (
          <p style={{ fontSize: 11, lineHeight: 1.6, color: 'var(--text-muted)', padding: '4px 4px' }}>
            Left-click an entity on either sheet to select it, then choose a status. Or right-click to add annotations.
          </p>
        )}

        {annotations.length > 0 && (
          <ChecklistSection
            key="custom_annotations"
            label="Annotations & Notes"
            statusLabel={String(annotations.length)}
            statusColor="#00e5ff"
            statusIsMatched={false}
            expanded={expanded['custom_annotations'] ?? true}
            onToggle={() =>
              setExpanded((prev) => ({
                ...prev,
                custom_annotations: !(prev['custom_annotations'] ?? true),
              }))
            }
          >
            {annotations.map((ann) => (
              <FindingCard
                key={ann.id}
                statusLabel={ann.severity.toUpperCase()}
                statusColor={
                  ann.severity === 'critical'
                    ? '#f43f5e'
                    : ann.severity === 'high'
                    ? '#f97316'
                    : ann.severity === 'medium'
                    ? '#eab308'
                    : '#00e5ff'
                }
                actions={
                  <button
                    type="button"
                    title="Delete annotation"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteAnnotationById(ann.id);
                    }}
                    style={{
                      background: 'transparent',
                      border: '1px solid transparent',
                      borderRadius: '4px',
                      color: '#f43f5e',
                      cursor: 'pointer',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '3px 6px',
                      position: 'relative',
                      zIndex: 10,
                      pointerEvents: 'auto',
                    }}
                  >
                    <Trash2 size={13} />
                    <span>Remove</span>
                  </button>
                }
              >
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>
                  {ann.content || 'Annotation Pin'}
                </div>
                {ann.coordinates && (
                  <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                    CAD Pos: ({Math.round(ann.coordinates[0])}, {Math.round(ann.coordinates[1])})
                  </div>
                )}
              </FindingCard>
            ))}
          </ChecklistSection>
        )}

        {CATEGORY_KEYS.map((key) => {
          const rows = grouped[key] ?? [];
          if (!rows.length) return null;
          // The same card the engine's checklist uses. It was a bold caption over bare rows,
          // which made this panel look like a different product sitting in the same slot — and
          // an engineer switching between an AI room and a manual one had to relearn the page.
          // Only the chrome is shared; the rows below are this panel's own, because recording a
          // judgement and correcting the engine's are different acts with different destinations.
          const allMatched = rows.every((m) => m.status === 'MATCHED');
          return (
            <ChecklistSection
              key={key}
              label={categoryLabel(key)}
              statusLabel={String(rows.length)}
              statusColor={
                allMatched ? MARKER_STYLES.MATCHED.color : MARKER_STYLES.CHANGED.color
              }
              statusIsMatched={allMatched}
              expanded={expanded[key] ?? true}
              onToggle={() =>
                setExpanded((prev) => ({ ...prev, [key]: !(prev[key] ?? true) }))
              }
            >
              {rows.map((m) => {
                // The card's own heading. A checklist row names a FIELD; a marking has no field,
                // so it heads with the value the engineer marked — the revision's spelling where
                // there is one, since that is the sheet being checked.
                const title = m.rev_text || m.ref_text || '—';
                return (
                  <FindingCard
                    key={m.id}
                    statusLabel={`${m.status.replace(/_/g, ' ')}${m.is_bulk ? ' · bulk' : ''}`}
                    statusColor={markerStyle(m.status).color}
                    actions={
                      /* Labelled "Remove" because that is what it means to the engineer using
                         it. The tooltip still states what happens on the server, because the two
                         differ and the difference matters if anyone ever needs a marking back:
                         nothing is deleted, the row is stamped `retracted_at` and hidden. */
                      <button
                        type="button"
                        title="Remove from this check — the record is kept on the server, marked as withdrawn"
                        onClick={() => retractManualMarking(m.id)}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: MARKER_STYLES.MISMATCHED.color,
                          cursor: 'pointer',
                          fontSize: '0.65rem',
                          fontWeight: 600,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '3px',
                          padding: 0,
                        }}
                      >
                        <Trash2 size={11} />
                        <span>Remove</span>
                      </button>
                    }
                  >
                    <ComparisonValues
                      title={title}
                      // Straight through. A `markingValueView` helper used to decide whether to
                      // show one value or two — a rule the compact row needed and this grid does
                      // not: two labelled columns are always drawn, and an absent side prints
                      // `-`, which for an ADDED or a REMOVED is the finding rather than a gap.
                      original={m.ref_text ?? ''}
                      revision={m.rev_text ?? ''}
                      struck={m.status === 'CHANGED' || m.status === 'REMOVED'}
                      matched={m.status === 'MATCHED'}
                      theme={theme}
                    />
                    {m.notes && (
                      <div style={{ fontSize: 10, lineHeight: 1.45, color: 'var(--text-muted)' }}>
                        {m.notes}
                      </div>
                    )}
                  </FindingCard>
                );
              })}
            </ChecklistSection>
          );
        })}
      </div>

      <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {isSubmitted ? (
          <>
            <div
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 700,
                background: 'rgba(16,185,129,0.15)',
                border: '1.5px solid #10b981',
                color: '#10b981',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
              }}
            >
              <CheckCircle2 size={14} /> Check Submitted
            </div>

            <button
              type="button"
              onClick={exportToPDF}
              disabled={isExporting}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
                background: 'rgba(0, 229, 255, 0.15)',
                border: '1.5px solid var(--accent-cyan)',
                color: 'var(--accent-cyan)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
              }}
              title="Download Compliance Audit Report PDF"
            >
              <Download size={14} /> {isExporting ? 'Building report…' : 'Export PDF Report'}
            </button>

            <ExportStatusNote status={exportStatus} onReveal={revealExport} />
            <ExportOverlay active={isExporting} phase={exportPhase} />

            <button
              type="button"
              onClick={async () => {
                setSubmitted(false);
                clearMarkingError();
                await reopenManualSession();
              }}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: 'transparent',
                border: '1.5px solid var(--border-color)',
                color: 'var(--text-main)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
              }}
            >
              <RotateCcw size={14} /> Re-open / Edit Check
            </button>
          </>
        ) : (
          <button
            type="button"
            disabled={!canSubmit}
            onClick={submit}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 700,
              cursor: canSubmit ? 'pointer' : 'not-allowed',
              background: canSubmit ? '#059669' : 'var(--bg-dark)',
              border: `1.5px solid ${canSubmit ? '#059669' : 'var(--border-color)'}`,
              color: canSubmit ? '#fff' : 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
            }}
          >
            {submitting ? 'Finalising…' : 'Finish check'}
          </button>
        )}
        <p style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2, textAlign: 'center' }}>
          Markings are saved as you stamp them.
        </p>
      </div>
    </div>
  );
};
