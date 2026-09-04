import { markerUi, markerStyle } from './markerStyles';
import { ChecklistSection } from './ChecklistSection';
import { ComparisonGridStyles, ComparisonValues, FindingCard } from './FindingCard';
import { useThemeStore } from '../../stores/themeStore';
import React, { useCallback, useMemo, useState } from 'react';
import {
  Trash2,
  Download,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useRoomStore } from '../../stores/roomStore';
import { useIsManualCheckRoom } from '../../hooks/useManualCheckRoom';
import { useComplianceReportExport } from '../../hooks/useComplianceReportExport';
import { CATEGORY_KEYS, categoryLabel } from './manualCheckCategories';
import { COMPARISON_TAXONOMY, getTaxonomyWithOther, inferFeatureKeyForPair, isTitleBlockText, OTHER_FEATURE_KEY } from '../../utils/comparisonTaxonomy';
import { ExportStatusNote } from './ExportStatusNote';
import { ExportOverlay } from './ExportOverlay';
import { StaleExtractionBadge } from './StaleExtractionBadge';
import { getAnnotationBadgeMap } from '../../stores/workspace/types';

/**
 * The live marking list — the whole left panel in a manual-check room.
 *
 * Renders inside the existing panel rather than as a new flexlayout tab, so the saved layout key
 * does not have to be bumped and nobody's arrangement resets.
 *
 * All six categories are shown, including the two the AI checklist omits: `isometric_view`
 * is one of the corpus's four recorded false-negative classes, and a category with no heading is
 * one an engineer does not think to look for.
 *
 * Colours are CSS variables so the panel follows `data-theme` with no branching. It previously
 * read `theme` off `reviewStore`, which does not have it — the selector returned `undefined` and
 * the dark styling was applied unconditionally.
 */

export const ManualMarkingList: React.FC = () => {
  const isManualCheckRoom = useIsManualCheckRoom();
  const theme = useThemeStore((s) => s.theme);

  const markings = useWorkspaceStore((s) => s.markings);
  const annotations = useWorkspaceStore((s) => s.annotations);
  const annotationBadgeMap = useMemo(() => getAnnotationBadgeMap(annotations), [annotations]);
  // Subscribed, not read through `getState()` like `retryOpen` does: the stale badge below has
  // to re-render when the pair changes, and `extraction_is_stale` arrives with the drawing.
  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const newDrawing = useWorkspaceStore((s) => s.newDrawing);
  const deleteAnnotationById = useWorkspaceStore((s) => s.deleteAnnotationById);
  const manualSessionId = useWorkspaceStore((s) => s.manualSessionId);
  const manualSessionError = useWorkspaceStore((s) => s.manualSessionError);
  const manualSessionStatus = useWorkspaceStore((s) => s.manualSessionStatus);
  const isSubmitted = manualSessionStatus === 'submitted' || manualSessionStatus === 'completed';
  const startManualSession = useWorkspaceStore((s) => s.startManualSession);
  const submitManualSession = useWorkspaceStore((s) => s.submitManualSession);
  const retractManualMarking = useWorkspaceStore((s) => s.retractManualMarking);
  const markingError = useWorkspaceStore((s) => s.markingError);
  const clearMarkingError = useWorkspaceStore((s) => s.clearMarkingError);
  const pendingPairRef = useWorkspaceStore((s) => s.pendingPairRef);
  const pendingPairTool = useWorkspaceStore((s) => s.pendingPairTool);

  const activeRoom = useRoomStore((s) => s.activeRoom);

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);

  const { isExporting, exportPhase, exportStatus, exportToPDF, revealExport } =
    useComplianceReportExport();

  const retryOpen = useCallback(() => {
    if (!activeRoom || !oldDrawing?.id || !newDrawing?.id) return;
    startManualSession(String(activeRoom.id), String(oldDrawing.id), String(newDrawing.id));
  }, [activeRoom, oldDrawing?.id, newDrawing?.id, startManualSession]);

  const grouped = useMemo(() => {
    const map: Record<string, typeof markings> = {};
    for (const key of CATEGORY_KEYS) map[key] = [];
    for (const m of markings) {
      const targetText = m.rev_text || m.ref_text || '';
      const effCat = (m.category === 'drawing_views' && isTitleBlockText(targetText))
        ? 'title_block'
        : (m.category || 'drawing_views');
      (map[effCat] ??= []).push(m);
    }
    return map;
  }, [markings]);

  if (!isManualCheckRoom) return null;

  /*
    Session submission is driven directly through `submitManualSession`, which writes to
    `manualSessionStatus` in the store upon server confirmation. Any marking modification
    on the canvas automatically flips the session back to in_progress.
  */
  const submit = async () => {
    setSubmitting(true);
    await submitManualSession();
    setSubmitting(false);
  };

  const totalCount = markings.length + annotations.length;
  const canSubmit = Boolean(manualSessionId) && totalCount > 0 && !submitting && !isSubmitted;

  const matchedCount = markings.filter((m) => m.status === 'MATCHED').length;
  const changedCount = markings.filter((m) => m.status === 'CHANGED' || m.status === 'MISMATCHED').length;
  const diffCount = markings.filter((m) => m.status === 'ADDED' || m.status === 'REMOVED').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div
        style={{
          padding: '10px 12px',
          borderBottom: '1px solid var(--border-color)',
          background: 'var(--bg-card)',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
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

          {totalCount > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {matchedCount > 0 && (
                <span
                  title={`${matchedCount} Matched`}
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: 999,
                    color: '#10b981',
                    background: 'rgba(16,185,129,0.12)',
                  }}
                >
                  ✓ {matchedCount}
                </span>
              )}
              {changedCount > 0 && (
                <span
                  title={`${changedCount} Changed / Mismatched`}
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: 999,
                    color: '#ff6b00',
                    background: 'rgba(255,107,0,0.12)',
                  }}
                >
                  ⚠ {changedCount}
                </span>
              )}
              {diffCount > 0 && (
                <span
                  title={`${diffCount} Added / Removed`}
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: 999,
                    color: '#a855f7',
                    background: 'rgba(168,85,247,0.12)',
                  }}
                >
                  ± {diffCount}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/*
        Stale-extraction warning for the pair being marked.

        This is the only place it can appear in a prototype build. `StaleExtractionBadge`
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
            color: markerUi('CHANGED', theme === 'hc-light').color,
            background: markerUi('CHANGED', theme === 'hc-light').background,
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
              color: markerUi('MISMATCHED', theme === 'hc-light').color,
              background: markerUi('MISMATCHED', theme === 'hc-light').background,
              border: `1px solid ${markerUi('MISMATCHED', theme === 'hc-light').color}44`,
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
              color: markerUi('MISMATCHED', theme === 'hc-light').color,
              background: markerUi('MISMATCHED', theme === 'hc-light').background,
              border: `1px solid ${markerUi('MISMATCHED', theme === 'hc-light').color}44`,
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
            label="Annotations"
            statusLabel={String(annotations.length)}
            statusColor={theme === 'hc-light' ? '#b91c1c' : '#ef4444'}
            statusIsMatched={false}
            expanded={expanded['custom_annotations'] ?? true}
            onToggle={() =>
              setExpanded((prev) => ({
                ...prev,
                custom_annotations: !(prev['custom_annotations'] ?? true),
              }))
            }
          >
            {annotations.map((ann) => {
              const badgeLabel = annotationBadgeMap[ann.id] || 'X';
              return (
                <FindingCard
                  key={ann.id}
                  statusLabel={badgeLabel}
                  statusColor={theme === 'hc-light' ? '#b91c1c' : '#ef4444'}
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
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '0.68rem',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '3px',
                      padding: '1px 4px',
                      borderRadius: '3px',
                      transition: 'color 0.15s ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = '#ef4444')}
                    onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                  >
                    <Trash2 size={12} />
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
            );
          })}
        </ChecklistSection>
        )}

        {CATEGORY_KEYS.map((key) => {
          const rows = grouped[key] ?? [];
          // Resolve every marking's sub-item ONCE, up front. The bucket list below and the rows
          // inside each bucket are both derived from this, so they cannot disagree about where a
          // marking went — the previous shape called `inferFeatureKey` inside the per-feature
          // filter, which meant the list of buckets and the contents of the buckets were two
          // separate readings of the same rule.
          // No explicit feature is passed because a manual marking cannot carry one:
          // `GroundTruthMarking` has `category`, `ref_text` and `rev_text` and nothing finer,
          // mirroring the backend model, and the stamp modal only offers the six categories. So
          // in a manual-check room `inferFeatureKey` is the WHOLE story for where a value the
          // engineer stamped shows up — which is why its BOM rules are worth reading closely.
          const resolved = rows.map((m) => ({
            m,
            feature: inferFeatureKeyForPair(key, m.ref_text, m.rev_text, undefined, m.feature),
          }));
          // `inferFeatureKey` returns `other` when nothing in the category confidently matches —
          // a real answer, not a failure. The named sub-items are always shown (an unchecked one
          // reads "Pending", which is the point of this panel); the Other bucket appears only
          // once something is in it, but it MUST appear then. Rendering `COMPARISON_TAXONOMY`
          // alone is how a marking an engineer actually stamped drops out of the panel with
          // nothing to show it ever existed — the same silent drop DEFERRED_FEATURE_KEYS warns
          // about in `comparisonTaxonomy.ts`, arriving from the other direction.
          const featureItems = resolved.some((r) => r.feature === OTHER_FEATURE_KEY)
            ? getTaxonomyWithOther(key)
            : (COMPARISON_TAXONOMY[key] ?? []);
          const isLight = theme === 'hc-light';
          const hasRows = rows.length > 0;
          const hasChanged = rows.some((m) => m.status !== 'MATCHED');
          const allMatched = hasRows && !hasChanged;

          let statusLabel = undefined;
          let sectionColor = 'var(--text-muted)';
          if (hasChanged) {
            const discCount = rows.filter((m) => m.status !== 'MATCHED').length;
            statusLabel = `${discCount} changed`;
            sectionColor = '#ff6b00';
          } else if (hasRows) {
            statusLabel = `${rows.length} checked`;
            sectionColor = markerUi('MATCHED', isLight).color;
          }

          const isCatExpanded = expanded[key] ?? (hasRows || key === 'drawing_views');

          return (
            <ChecklistSection
              key={key}
              label={categoryLabel(key)}
              statusLabel={statusLabel}
              statusColor={sectionColor}
              statusIsMatched={allMatched}
              expanded={isCatExpanded}
              onToggle={() =>
                setExpanded((prev) => ({ ...prev, [key]: !isCatExpanded }))
              }
            >
              <div
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 6,
                  overflow: 'hidden',
                }}
              >
                {featureItems.map((feat, idx) => {
                  const featRows = resolved.filter((r) => r.feature === feat.key).map((r) => r.m);
                  const featHasRows = featRows.length > 0;
                  const featHasChanged = featRows.some((m) => m.status !== 'MATCHED');
                  const featAllMatched = featHasRows && !featHasChanged;
                  const isLast = idx === featureItems.length - 1;

                  const featPillColor = featHasChanged
                    ? '#ff6b00'
                    : featAllMatched
                    ? markerUi('MATCHED', isLight).color
                    : 'var(--text-muted)';

                  const featExpandedKey = `${key}_${feat.key}`;
                  const isFeatExpanded = expanded[featExpandedKey] ?? featHasRows;

                  return (
                    <div
                      key={feat.key}
                      style={{
                        borderBottom: isLast && (!isFeatExpanded || !featHasRows) ? 'none' : '1px solid var(--border-color)',
                      }}
                    >
                      <div
                        onClick={() => {
                          if (featHasRows) {
                            setExpanded((prev) => ({
                              ...prev,
                              [featExpandedKey]: !isFeatExpanded,
                            }));
                          }
                        }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '7px 10px',
                          cursor: featHasRows ? 'pointer' : 'default',
                          userSelect: 'none',
                          background: isFeatExpanded && featHasRows ? 'var(--sidebar-item-hover)' : 'transparent',
                          transition: 'background 0.15s ease',
                        }}
                      >
                        {/* Left: subtle status indicator dot + label */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, flex: 1 }}>
                          {featHasChanged ? (
                            <span
                              title="Discrepancy recorded"
                              style={{
                                width: 7,
                                height: 7,
                                borderRadius: '50%',
                                background: '#ff6b00',
                                boxShadow: '0 0 5px rgba(255, 107, 0, 0.7)',
                                flexShrink: 0,
                              }}
                            />
                          ) : featAllMatched ? (
                            <span
                              title="All matched"
                              style={{
                                width: 7,
                                height: 7,
                                borderRadius: '50%',
                                background: '#10b981',
                                boxShadow: '0 0 5px rgba(16, 185, 129, 0.7)',
                                flexShrink: 0,
                              }}
                            />
                          ) : (
                            <span
                              title="Pending"
                              style={{
                                width: 7,
                                height: 7,
                                borderRadius: '50%',
                                border: '1.5px solid var(--text-muted)',
                                opacity: 0.35,
                                flexShrink: 0,
                              }}
                            />
                          )}
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: featHasRows ? 700 : 500,
                              color: featHasRows ? 'var(--text-primary)' : 'var(--text-muted)',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {feat.label}
                          </span>
                        </div>

                        {/* Right: compact status pill or subtle pending */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                          {featHasRows ? (
                            <>
                              <span
                                style={{
                                  fontSize: 10,
                                  fontWeight: 700,
                                  color: featPillColor,
                                  background: `${featPillColor}18`,
                                  padding: '1px 6px',
                                  borderRadius: 999,
                                }}
                              >
                                {featHasChanged
                                  ? `${featRows.filter((m) => m.status !== 'MATCHED').length} changed`
                                  : `✓ ${featRows.length}`}
                              </span>
                              {isFeatExpanded ? (
                                <ChevronDown size={12} color="var(--text-muted)" />
                              ) : (
                                <ChevronRight size={12} color="var(--text-muted)" />
                              )}
                            </>
                          ) : (
                            <span
                              style={{
                                fontSize: 10,
                                color: 'var(--text-muted)',
                                opacity: 0.35,
                                fontWeight: 500,
                              }}
                            >
                              Pending
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Findings Tray (only when markings are recorded!) */}
                      {isFeatExpanded && featHasRows && (
                        <div
                          style={{
                            padding: '8px 10px',
                            background: 'var(--bg-dark)',
                            borderTop: '1px solid var(--border-color)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 6,
                          }}
                        >
                          {featRows.map((m) => {
                            const { color: statusColor, background: statusBg } = markerUi(m.status, isLight);
                            const glyph = m.status === 'MISMATCHED' ? '✕' : (markerStyle(m.status)?.glyph || '✓');
                            const iconBadge = `${glyph}${m.is_bulk ? ' · bulk' : ''}`;
                            return (
                              <FindingCard
                                key={m.id}
                                statusLabel={iconBadge}
                                statusColor={statusColor}
                                statusBg={statusBg}
                                actions={
                                  <button
                                    type="button"
                                    title="Remove from this check"
                                    onClick={() => retractManualMarking(m.id)}
                                    style={{
                                      background: 'transparent',
                                      border: 'none',
                                      color: 'var(--text-muted)',
                                      cursor: 'pointer',
                                      fontSize: '0.68rem',
                                      fontWeight: 600,
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: '3px',
                                      padding: '1px 4px',
                                      borderRadius: '3px',
                                      transition: 'color 0.15s ease',
                                    }}
                                    onMouseEnter={(e) => (e.currentTarget.style.color = '#ef4444')}
                                    onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                                  >
                                    <Trash2 size={12} />
                                    <span>Remove</span>
                                  </button>
                                }
                              >
                                <ComparisonValues
                                  original={m.ref_text ?? ''}
                                  revision={m.rev_text ?? ''}
                                  struck={m.status === 'CHANGED' || m.status === 'REMOVED'}
                                  matched={m.status === 'MATCHED'}
                                  added={m.status === 'ADDED'}
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
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </ChecklistSection>
          );
        })}
      </div>

      <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {isSubmitted ? (
          <>
            <button
              type="button"
              onClick={exportToPDF}
              disabled={isExporting}
              style={{
                width: '100%',
                padding: '9px 12px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 700,
                cursor: isExporting ? 'wait' : 'pointer',
                background: 'rgba(0, 229, 255, 0.15)',
                border: '1.5px solid var(--accent-cyan)',
                color: 'var(--accent-cyan)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
                transition: 'all 0.15s ease',
              }}
              title="Download Compliance Audit Report PDF"
            >
              <Download size={14} /> {isExporting ? 'Building report…' : 'Export PDF Report'}
            </button>

            <ExportStatusNote status={exportStatus} onReveal={revealExport} />
            <ExportOverlay active={isExporting} phase={exportPhase} />
          </>
        ) : (
          <button
            type="button"
            disabled={!canSubmit}
            onClick={submit}
            style={{
              width: '100%',
              padding: '9px 12px',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 700,
              cursor: canSubmit ? 'pointer' : 'not-allowed',
              background: canSubmit ? '#10b981' : 'var(--sidebar-item-hover)',
              border: `1.5px solid ${canSubmit ? '#10b981' : 'var(--border-color)'}`,
              color: canSubmit ? '#fff' : 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              boxShadow: canSubmit ? '0 2px 8px rgba(16, 185, 129, 0.35)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            {submitting ? 'Finalising…' : canSubmit ? `Finish check (${totalCount} item${totalCount === 1 ? '' : 's'})` : 'Finish check'}
          </button>
        )}
        <p style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2, textAlign: 'center' }}>
          Markings are saved as you stamp them.
        </p>
      </div>
    </div>
  );
};
