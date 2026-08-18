import React, { useEffect, useMemo, useState } from 'react';
import { X, AlertTriangle } from 'lucide-react';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { CATEGORY_OPTIONS } from './manualCheckCategories';

/**
 * Where a stamp acquires its meaning.
 *
 * ## Why this dialog is mandatory rather than a convenience
 *
 * The marker the product already had recorded `category: 'Manual Marker'`, `description:
 * 'Manually added marker'`, `affected_entities: []` — that a human pointed at a place, and
 * nothing about what they saw there. Nothing can learn from it: the trainer's primary feature is
 * `text_combined`, and with no entity there is no text.
 *
 * A marking is usable only if the click captures all four of an addressable entity, both sides'
 * text, a real taxonomy category, and a verdict. Three arrive from the canvas; this collects the
 * category and refuses to close without it.
 *
 * ## Theming
 *
 * Every colour here is a CSS variable, so the dialog follows `data-theme` with no branching.
 * It previously read `theme` off `reviewStore`, which does not have it — the selector returned
 * `undefined`, `light` was permanently false, and the labels rendered dark-on-dark in light
 * mode. A token cannot be wrong that way: there is no second code path to keep in step.
 */

const STATUS_LABEL: Record<string, string> = {
  matched: 'MATCHED',
  added: 'ADDED',
  removed: 'REMOVED',
  changed: 'CHANGED',
  not_a_finding: 'NOT A FINDING',
};

const STATUS_ACCENT: Record<string, string> = {
  matched: '#10b981',
  added: '#3b82f6',
  removed: '#ef4444',
  changed: '#f97316',
  not_a_finding: '#a1a1aa',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 10,
  fontWeight: 800,
  letterSpacing: '0.09em',
  textTransform: 'uppercase',
  color: 'var(--text-secondary)',
  marginBottom: 6,
};

const fieldStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  background: 'var(--bg-dark)',
  border: '1.5px solid var(--border-color)',
  borderRadius: 8,
  padding: '8px 12px',
  fontSize: 13,
  color: 'var(--text-primary)',
  outline: 'none',
};

export const StampMarkingModal: React.FC = () => {
  const pendingStamp = useWorkspaceStore((s) => s.pendingStamp);
  const openStamp = useWorkspaceStore((s) => s.openStamp);
  const commitStamp = useWorkspaceStore((s) => s.commitStamp);

  const [category, setCategory] = useState('');
  const [refText, setRefText] = useState('');
  const [revText, setRevText] = useState('');
  const [notes, setNotes] = useState('');
  // The engineer's own call: one record standing for a group of similar entities. Nothing on
  // the canvas can infer it now that selection is one entity at a time, so it starts unticked.
  const [isBulk, setIsBulk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Raw entity text, kept so an override stays visible rather than being discovered later as a
  // label that disagrees with its own entity.
  const rawRef = pendingStamp?.ref?.text ?? '';
  const rawRev = pendingStamp?.rev?.text ?? '';

  useEffect(() => {
    if (!pendingStamp) return;
    setCategory(''); // never pre-filled — see the note on the selector below
    setRefText(rawRef);
    setRevText(rawRev);
    setNotes('');
    setIsBulk(false);
    setError(null);
  }, [pendingStamp, rawRef, rawRev]);

  const addresses = useMemo(
    () =>
      [
        pendingStamp?.ref ? { side: 'Reference', picked: pendingStamp.ref } : null,
        pendingStamp?.rev ? { side: 'Revision', picked: pendingStamp.rev } : null,
      ].filter(Boolean) as { side: string; picked: any }[],
    [pendingStamp],
  );

  // Escape closes, so a mis-click is one key away from undone rather than requiring the mouse.
  useEffect(() => {
    if (!pendingStamp) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') openStamp(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pendingStamp, openStamp]);

  if (!pendingStamp) return null;

  const textWasEdited = refText !== rawRef || revText !== rawRev;
  const canSave = Boolean(category) && !busy;
  const accent = STATUS_ACCENT[pendingStamp.tool] ?? 'var(--accent-cyan)';

  const save = async () => {
    if (!canSave) return;
    setBusy(true);
    setError(null);
    try {
      await commitStamp({ category, refText, revText, textWasEdited, isBulk, notes });
    } catch (err: any) {
      // Left open with the engineer's typing intact. Closing here would discard a judgement they
      // already made and give no sign it was never recorded.
      setError(err?.message ?? 'Could not record this marking. It has not been saved.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.45)',
        backdropFilter: 'blur(2px)',
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) openStamp(null);
      }}
    >
      <div
        style={{
          width: 440,
          maxHeight: '86vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-card)',
          border: '1.5px solid var(--border-color)',
          borderRadius: 16,
          boxShadow: '0 24px 60px rgba(0,0,0,0.35)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 18px',
            borderBottom: '1px solid var(--border-color)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <span
              style={{ width: 8, height: 8, borderRadius: 999, background: accent, flexShrink: 0 }}
            />
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
              Record marking
            </span>
            <span
              style={{
                fontSize: 10,
                fontWeight: 800,
                letterSpacing: '0.08em',
                color: accent,
                background: `${accent}1f`,
                padding: '3px 7px',
                borderRadius: 6,
              }}
            >
              {STATUS_LABEL[pendingStamp.tool]}
            </span>
          </div>
          <button
            type="button"
            onClick={() => openStamp(null)}
            aria-label="Close"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex' }}
          >
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>
          {/* Address: display only. It says which entity was clicked; editing it would turn the
              marking into a statement about something the annotator never looked at. */}
          <div>
            <label style={labelStyle}>Entity</label>
            {addresses.map(({ side, picked }) => (
              <div
                key={side}
                style={{
                  fontFamily: 'ui-monospace, monospace',
                  fontSize: 11,
                  color: 'var(--text-muted)',
                  background: 'var(--bg-dark)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 8,
                  padding: '7px 10px',
                  marginBottom: 6,
                  wordBreak: 'break-all',
                }}
              >
                <span style={{ color: 'var(--text-secondary)', fontWeight: 700 }}>{side}</span>
                {` · ${picked.entityType}`}
                {picked.handle ? ` · handle ${picked.handle}` : ' · no handle (block child)'}
                {` · layer ${picked.layer}`}
              </div>
            ))}
          </div>

          {(pendingStamp.ref || pendingStamp.tool === 'changed') && (
            <div>
              <label style={labelStyle}>Reference text</label>
              <input style={fieldStyle} value={refText} onChange={(e) => setRefText(e.target.value)} />
            </div>
          )}

          {(pendingStamp.rev || pendingStamp.tool === 'changed') && (
            <div>
              <label style={labelStyle}>Revision text</label>
              <input style={fieldStyle} value={revText} onChange={(e) => setRevText(e.target.value)} />
            </div>
          )}

          {textWasEdited && (
            <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 11, color: '#f59e0b', lineHeight: 1.45 }}>
              <AlertTriangle size={13} style={{ marginTop: 1, flexShrink: 0 }} />
              <span>
                Text differs from the entity. Recorded as an override, with the raw value kept
                alongside it.
              </span>
            </div>
          )}

          <div>
            <label style={labelStyle}>
              Category <span style={{ color: '#ef4444' }}>*</span>
            </label>
            {/* Deliberately empty until chosen. `zone_ownership` could pre-fill this and must
                not: that would make the engineer's answer a copy of the engine's, and category
                attribution is the one non-tautological figure this corpus has produced. */}
            <select style={fieldStyle} value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Choose a category…</option>
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.key} value={opt.key}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer', fontSize: 12, lineHeight: 1.45, color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={isBulk}
              onChange={(e) => setIsBulk(e.target.checked)}
              style={{ marginTop: 2, accentColor: accent }}
            />
            <span>
              One editorial act covering several entities — a whole added view is{' '}
              <strong style={{ color: 'var(--text-primary)' }}>one</strong> marking anchored here,
              not forty.
            </span>
          </label>

          <div>
            <label style={labelStyle}>Notes</label>
            <textarea
              style={{ ...fieldStyle, height: 64, resize: 'none', lineHeight: 1.5 }}
              placeholder="Why this is what it is. Read when a disagreement is investigated."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {error && (
            <div
              style={{
                fontSize: 11,
                color: '#ef4444',
                background: 'rgba(239,68,68,0.12)',
                border: '1px solid rgba(239,68,68,0.35)',
                borderRadius: 8,
                padding: '7px 10px',
              }}
            >
              {error}
            </div>
          )}
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 8,
            padding: '12px 18px',
            borderTop: '1px solid var(--border-color)',
          }}
        >
          <button
            type="button"
            onClick={() => openStamp(null)}
            style={{
              background: 'none',
              border: '1.5px solid var(--border-color)',
              borderRadius: 8,
              padding: '7px 14px',
              fontSize: 12,
              color: 'var(--text-secondary)',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canSave}
            onClick={save}
            title={category ? undefined : 'Choose a category first'}
            style={{
              background: canSave ? accent : 'var(--bg-dark)',
              border: `1.5px solid ${canSave ? accent : 'var(--border-color)'}`,
              borderRadius: 8,
              padding: '7px 16px',
              fontSize: 12,
              fontWeight: 700,
              color: canSave ? '#fff' : 'var(--text-muted)',
              cursor: canSave ? 'pointer' : 'not-allowed',
            }}
          >
            {busy ? 'Recording…' : 'Record marking'}
          </button>
        </div>
      </div>
    </div>
  );
};
