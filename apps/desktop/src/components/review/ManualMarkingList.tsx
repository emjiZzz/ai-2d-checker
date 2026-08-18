import React, { useMemo, useState } from 'react';
import { Undo2, CheckCircle2, ClipboardCheck } from 'lucide-react';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useIsManualCheckRoom } from '../../hooks/useManualCheckRoom';
import { CATEGORY_KEYS, categoryLabel } from './manualCheckCategories';

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
import { MARKING_STATUS_STYLE } from './renderManualMarkings';

export const ManualMarkingList: React.FC = () => {
  const isManualCheckRoom = useIsManualCheckRoom();

  const markings = useWorkspaceStore((s) => s.markings);
  const manualSessionId = useWorkspaceStore((s) => s.manualSessionId);
  const pendingPairRef = useWorkspaceStore((s) => s.pendingPairRef);
  const retractManualMarking = useWorkspaceStore((s) => s.retractManualMarking);
  const submitManualSession = useWorkspaceStore((s) => s.submitManualSession);

  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const grouped = useMemo(() => {
    const map: Record<string, typeof markings> = {};
    for (const key of CATEGORY_KEYS) map[key] = [];
    for (const m of markings) (map[m.category] ??= []).push(m);
    return map;
  }, [markings]);

  if (!isManualCheckRoom) return null;

  const submit = async () => {
    setSubmitting(true);
    await submitManualSession();
    setSubmitting(false);
    setSubmitted(true);
  };

  const canSubmit = Boolean(manualSessionId) && markings.length > 0 && !submitting;

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
            Manual Engineer Check
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>
            {manualSessionId
              ? `${markings.length} marking${markings.length === 1 ? '' : 's'} recorded`
              : 'Opening session…'}
          </div>
        </div>
      </div>

      {/* A pairing in flight, surfaced here as well as in the menu. Without it the first half of
          a CHANGED pair is invisible state, and a click that appears to do nothing is how a user
          concludes the tool is broken. */}
      {pendingPairRef && (
        <div
          style={{
            padding: '7px 12px',
            fontSize: 11,
            lineHeight: 1.45,
            color: '#f97316',
            background: 'rgba(249,115,22,0.1)',
            borderBottom: '1px solid var(--border-color)',
          }}
        >
          Pairing “{pendingPairRef.text || pendingPairRef.entityType}” — right-click its
          counterpart on the revision.
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 8px 12px' }}>
        {markings.length === 0 && (
          <p style={{ fontSize: 11, lineHeight: 1.6, color: 'var(--text-muted)', padding: '4px 4px' }}>
            Right-click an entity on either sheet to record a finding. Nothing here is produced by
            the engine — this list is only what you have recorded.
          </p>
        )}

        {CATEGORY_KEYS.map((key) => {
          const rows = grouped[key] ?? [];
          if (!rows.length) return null;
          return (
            <div key={key} style={{ marginBottom: 12 }}>
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: 'var(--text-secondary)',
                  padding: '0 4px 5px',
                }}
              >
                {categoryLabel(key)} · {rows.length}
              </div>
              {rows.map((m) => (
                <div
                  key={m.id}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 7,
                    padding: '7px 8px',
                    marginBottom: 4,
                    borderRadius: 8,
                    background: 'var(--bg-dark)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  <span
                    style={{
                      marginTop: 4,
                      width: 6,
                      height: 6,
                      borderRadius: 999,
                      flexShrink: 0,
                      background: MARKING_STATUS_STYLE[m.status]?.color ?? '#a1a1aa',
                    }}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', color: 'var(--text-secondary)' }}>
                      {m.status.replace(/_/g, ' ')}
                      {m.is_bulk && <span style={{ color: 'var(--text-muted)' }}> · bulk</span>}
                    </div>
                    <div
                      style={{
                        fontFamily: 'ui-monospace, monospace',
                        fontSize: 11,
                        color: 'var(--text-primary)',
                        wordBreak: 'break-word',
                        marginTop: 2,
                      }}
                    >
                      {m.status === 'CHANGED'
                        ? `${m.ref_text || '∅'} → ${m.rev_text || '∅'}`
                        : m.rev_text || m.ref_text || '—'}
                    </div>
                    {m.notes && (
                      <div style={{ fontSize: 10, lineHeight: 1.45, color: 'var(--text-muted)', marginTop: 3 }}>
                        {m.notes}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    title="Retract — the record is marked, never deleted"
                    onClick={() => retractManualMarking(m.id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'var(--text-muted)',
                      padding: 0,
                      display: 'flex',
                      flexShrink: 0,
                    }}
                  >
                    <Undo2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border-color)' }}>
        {/* Submit finalises a session that already holds its data — every marking was persisted
            as it was stamped. The wording says so: a button labelled "save" implies the opposite
            and invites an engineer to worry about losing work they cannot lose. */}
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
          {submitted ? (
            <>
              <CheckCircle2 size={13} /> Check submitted
            </>
          ) : submitting ? (
            'Finalising…'
          ) : (
            'Finish check'
          )}
        </button>
        <p style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6, textAlign: 'center' }}>
          Markings are saved as you stamp them.
        </p>
      </div>
    </div>
  );
};
