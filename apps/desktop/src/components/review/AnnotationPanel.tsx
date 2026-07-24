import React, { useState, useMemo, useEffect } from 'react';
import { Trash2, MapPin, Check, Edit2, Search, Filter, X } from 'lucide-react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { AnnotationSeverity, SEVERITY_PEN_MAP, getAnnotationBadgeMap } from '../../stores/workspace/types';

const SEVERITY_BADGE_STYLE: Record<AnnotationSeverity, { label: string; bg: string; text: string }> = {
  info: { label: 'INFO', bg: 'bg-blue-500/10 border-blue-500/30', text: 'text-blue-400' },
  low: { label: 'LOW', bg: 'bg-cyan-500/10 border-cyan-500/30', text: 'text-cyan-400' },
  medium: { label: 'MED', bg: 'bg-yellow-500/10 border-yellow-500/30', text: 'text-yellow-400' },
  high: { label: 'HIGH', bg: 'bg-orange-500/10 border-orange-500/30', text: 'text-orange-400' },
  critical: { label: 'CRIT', bg: 'bg-red-500/10 border-red-500/30', text: 'text-red-400' },
};

const parseUtcDate = (dateStr: string | null | undefined): Date => {
  if (!dateStr) return new Date();
  const utcStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  return new Date(utcStr);
};

export const AnnotationPanel: React.FC = () => {
  const selectedViolationId = useReviewStore(s => s.selectedViolationId);

  const annotations = useWorkspaceStore(s => s.annotations);
  const selectedAnnotationId = useWorkspaceStore(s => s.selectedAnnotationId);
  const isPlacingAnnotation = useWorkspaceStore(s => s.isPlacingAnnotation);
  const pendingText = useWorkspaceStore(s => s.pendingAnnotationText);
  const pendingSeverity = useWorkspaceStore(s => s.pendingAnnotationSeverity || 'info');
  const newDrawing = useWorkspaceStore(s => s.newDrawing);
  const oldDrawing = useWorkspaceStore(s => s.oldDrawing);

  const fetchAnnotations = useWorkspaceStore(s => s.fetchAnnotations);
  const deleteAnnotationById = useWorkspaceStore(s => s.deleteAnnotationById);
  const updateAnnotationDetails = useWorkspaceStore(s => s.updateAnnotationDetails);
  const updateAnnotationStatus = useWorkspaceStore(s => s.updateAnnotationStatus);
  const selectAnnotation = useWorkspaceStore(s => s.selectAnnotation);
  const setIsPlacingAnnotation = useWorkspaceStore(s => s.setIsPlacingAnnotation);
  const setPendingAnnotationText = useWorkspaceStore(s => s.setPendingAnnotationText);
  const setPendingAnnotationSeverity = useWorkspaceStore(s => s.setPendingAnnotationSeverity);

  // Client-side filtering & search states
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'resolved'>('all');
  const [drawingFilter, setDrawingFilter] = useState<'all' | 'ref' | 'rev'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Inline editing state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editSeverity, setEditSeverity] = useState<AnnotationSeverity>('info');

  const activeDrawing = newDrawing || oldDrawing;

  useEffect(() => {
    if (activeDrawing) fetchAnnotations(activeDrawing.id);
  }, [activeDrawing?.id, fetchAnnotations]);

  // Centralized badge map: assigns A001, A002... to all annotations deterministically
  const annotationBadgeMap = useMemo(() => getAnnotationBadgeMap(annotations), [annotations]);

  // Client-side filtered list
  const filteredAnnotations = useMemo(() => {
    return annotations.filter((ann) => {
      if (statusFilter !== 'all' && ann.status !== statusFilter) return false;

      if (drawingFilter === 'ref' && oldDrawing && ann.drawing_id !== oldDrawing.id) return false;
      if (drawingFilter === 'rev' && newDrawing && ann.drawing_id !== newDrawing.id) return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesContent = ann.content.toLowerCase().includes(q);
        const matchesAuthor = ann.author_id.toLowerCase().includes(q);
        const badge = annotationBadgeMap[ann.id] || '';
        const matchesBadge = badge.toLowerCase().includes(q);
        if (!matchesContent && !matchesAuthor && !matchesBadge) return false;
      }
      return true;
    });
  }, [annotations, statusFilter, drawingFilter, searchQuery, oldDrawing, newDrawing, annotationBadgeMap]);

  const handleStartPlacing = () => {
    if (!pendingText.trim() || !activeDrawing) return;
    setIsPlacingAnnotation(true);
  };

  const handleStartEdit = (ann: typeof annotations[0]) => {
    setEditingId(ann.id);
    setEditContent(ann.content);
    setEditSeverity(ann.severity as AnnotationSeverity);
  };

  const handleSaveEdit = async (id: string) => {
    if (!editContent.trim()) return;
    await updateAnnotationDetails(id, {
      content: editContent.trim(),
      severity: editSeverity,
      pen_type: SEVERITY_PEN_MAP[editSeverity] || 'checker_blue',
    });
    setEditingId(null);
  };

  return (
    <div className="annotation-panel bg-bg-sidebar text-text-primary p-4 flex flex-col h-full border-l border-border-color style={{ width: '320px' }}">
      <div className="flex items-center justify-between border-b border-border-color pb-2 mb-3">
        <h2 className="text-lg font-bold">Reviewer Annotations</h2>
        <span className="text-xs bg-bg-card px-2 py-0.5 rounded border border-border-color text-accent-cyan font-mono">
          {filteredAnnotations.length} / {annotations.length}
        </span>
      </div>

      {selectedViolationId && (
        <div className="bg-red-500/10 text-red-500 p-2 rounded mb-3 text-xs border border-red-500/20">
          Linked to Active Violation: <span className="font-mono">{selectedViolationId.substring(0, 8)}...</span>
        </div>
      )}

      {isPlacingAnnotation && (
        <div className="bg-accent-cyan/10 text-accent-cyan p-2 rounded mb-3 text-xs border border-accent-cyan/20 flex items-center gap-2">
          <MapPin size={14} className="animate-bounce" /> Click on drawing to place your pin.
        </div>
      )}

      {/* Filter & Search Toolbar */}
      <div className="space-y-2 mb-3">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-2.5 text-text-muted" />
          <input
            type="text"
            className="w-full bg-bg-card text-text-primary text-xs pl-8 pr-7 py-1.5 rounded border border-border-color focus:border-accent-cyan outline-none"
            placeholder="Search notes, author, or badge..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-2 text-text-muted hover:text-text-primary"
            >
              <X size={12} />
            </button>
          )}
        </div>

        <div className="flex items-center justify-between gap-1 text-[11px]">
          <div className="flex items-center gap-1 bg-bg-card p-1 rounded border border-border-color flex-1">
            <Filter size={11} className="text-text-muted ml-0.5" />
            <button
              className={`px-1.5 py-0.5 rounded font-medium transition-colors ${statusFilter === 'all' ? 'bg-accent-cyan text-on-accent' : 'text-text-muted hover:text-text-primary'}`}
              onClick={() => setStatusFilter('all')}
            >
              All
            </button>
            <button
              className={`px-1.5 py-0.5 rounded font-medium transition-colors ${statusFilter === 'open' ? 'bg-accent-cyan text-on-accent' : 'text-text-muted hover:text-text-primary'}`}
              onClick={() => setStatusFilter('open')}
            >
              Open
            </button>
            <button
              className={`px-1.5 py-0.5 rounded font-medium transition-colors ${statusFilter === 'resolved' ? 'bg-accent-cyan text-on-accent' : 'text-text-muted hover:text-text-primary'}`}
              onClick={() => setStatusFilter('resolved')}
            >
              Done
            </button>
          </div>

          {(oldDrawing || newDrawing) && (
            <select
              className="bg-bg-card text-text-primary text-[11px] py-1 px-1 rounded border border-border-color outline-none"
              value={drawingFilter}
              onChange={(e: any) => setDrawingFilter(e.target.value)}
            >
              <option value="all">All Draw</option>
              {oldDrawing && <option value="ref">Ref</option>}
              {newDrawing && <option value="rev">Rev</option>}
            </select>
          )}
        </div>
      </div>

      {/* Annotations List */}
      <div className="flex-1 overflow-y-auto space-y-2.5 mb-3 pr-1">
        {!activeDrawing ? (
          <p className="text-text-muted text-sm text-center mt-10">Open a drawing to add annotations.</p>
        ) : filteredAnnotations.length === 0 ? (
          <p className="text-text-muted text-xs text-center mt-8">No matching annotations found.</p>
        ) : (
          filteredAnnotations.map((ann) => {
            const isSelected = selectedAnnotationId === ann.id;
            const isEditing = editingId === ann.id;
            const badgeCode = annotationBadgeMap[ann.id] || 'A000';
            const sevInfo = SEVERITY_BADGE_STYLE[(ann.severity as AnnotationSeverity) || 'info'];

            return (
              <div
                key={ann.id}
                onClick={() => selectAnnotation(ann.id)}
                className={`bg-bg-card border p-2.5 rounded text-xs cursor-pointer transition-colors ${
                  isSelected ? 'border-accent-cyan ring-1 ring-accent-cyan/30' : 'border-border-color hover:border-accent-cyan/40'
                } ${ann.status === 'resolved' ? 'opacity-60' : ''}`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono font-bold px-1.5 py-0.5 rounded text-[10px] bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/30">
                      {badgeCode}
                    </span>
                    <span className={`px-1 py-0.2 text-[9px] font-bold rounded border ${sevInfo.bg} ${sevInfo.text}`}>
                      {sevInfo.label}
                    </span>
                  </div>
                  <span className="text-[10px] text-text-muted">{parseUtcDate(ann.created_at).toLocaleDateString()}</span>
                </div>

                <div className="text-[10px] uppercase tracking-wide text-text-muted mb-1 truncate">
                  {ann.drawing_id === newDrawing?.id
                    ? `[Rev] ${newDrawing?.file_name}`
                    : ann.drawing_id === oldDrawing?.id
                      ? `[Ref] ${oldDrawing?.file_name}`
                      : 'Unknown Drawing'}
                </div>

                {isEditing ? (
                  <div className="space-y-2 my-2" onClick={(e) => e.stopPropagation()}>
                    <textarea
                      className="w-full bg-bg-sidebar text-text-primary text-xs p-1.5 rounded border border-accent-cyan outline-none resize-none"
                      rows={2}
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                    />
                    <div className="flex items-center justify-between gap-1">
                      <div className="flex gap-1">
                        {(['info', 'low', 'medium', 'high', 'critical'] as AnnotationSeverity[]).map((s) => (
                          <button
                            key={s}
                            type="button"
                            className={`px-1.5 py-0.5 text-[9px] font-bold rounded border ${
                              editSeverity === s ? 'bg-accent-cyan text-on-accent' : 'bg-bg-card text-text-muted border-border-color'
                            }`}
                            onClick={() => setEditSeverity(s)}
                          >
                            {s[0].toUpperCase()}
                          </button>
                        ))}
                      </div>
                      <div className="flex gap-1">
                        <button
                          className="px-2 py-0.5 bg-accent-cyan text-on-accent text-[10px] font-bold rounded"
                          onClick={() => handleSaveEdit(ann.id)}
                        >
                          Save
                        </button>
                        <button
                          className="px-1.5 py-0.5 bg-bg-card text-text-muted text-[10px] rounded border border-border-color"
                          onClick={() => setEditingId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className={`text-text-secondary my-1 ${ann.status === 'resolved' ? 'line-through' : ''}`}>
                    {ann.content}
                  </p>
                )}

                {ann.violation_id && (
                  <div className="text-[10px] text-red-400/80 bg-red-500/5 px-1.5 py-0.5 rounded border border-red-500/10 mt-1 truncate">
                    Linked to violation {ann.violation_id.substring(0, 8)}
                  </div>
                )}

                <div className="flex justify-between items-center mt-2 pt-1 border-t border-border-color/50 text-[10px] text-text-muted">
                  <span>By {ann.author_id}</span>
                  <div className="flex items-center gap-2">
                    <button
                      className="hover:text-accent-cyan transition-colors"
                      title="Edit note & severity"
                      onClick={(e) => { e.stopPropagation(); handleStartEdit(ann); }}
                    >
                      <Edit2 size={13} />
                    </button>
                    <button
                      className="hover:text-green-500 transition-colors"
                      title={ann.status === 'resolved' ? 'Reopen' : 'Mark resolved'}
                      onClick={(e) => { e.stopPropagation(); updateAnnotationStatus(ann.id, ann.status === 'resolved' ? 'open' : 'resolved'); }}
                    >
                      <Check size={13} />
                    </button>
                    <button
                      className="hover:text-red-500 transition-colors"
                      title="Delete annotation"
                      onClick={(e) => { e.stopPropagation(); deleteAnnotationById(ann.id); }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Creation Form */}
      <div className="mt-auto pt-2 border-t border-border-color">
        <div className="mb-2">
          <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider block mb-1">
            Annotation Severity
          </label>
          <div className="grid grid-cols-5 gap-1">
            {(['info', 'low', 'medium', 'high', 'critical'] as AnnotationSeverity[]).map((sev) => {
              const info = SEVERITY_BADGE_STYLE[sev];
              const isSelected = pendingSeverity === sev;
              return (
                <button
                  key={sev}
                  type="button"
                  className={`py-1 text-[10px] font-bold rounded border transition-colors ${
                    isSelected ? `${info.bg} ${info.text} ring-1 ring-accent-cyan` : 'bg-bg-card text-text-muted border-border-color hover:border-text-muted'
                  }`}
                  onClick={() => setPendingAnnotationSeverity(sev)}
                >
                  {info.label}
                </button>
              );
            })}
          </div>
        </div>

        <textarea
          className="w-full bg-bg-card text-text-primary text-xs p-2 rounded border border-border-color focus:border-accent-cyan outline-none resize-none disabled:opacity-50"
          rows={2}
          placeholder="Add engineering review note..."
          value={pendingText}
          disabled={!activeDrawing}
          onChange={(e) => setPendingAnnotationText(e.target.value)}
        />
        <button
          className="w-full bg-accent-cyan text-on-accent font-bold py-2 px-3 rounded mt-2 text-xs transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={!activeDrawing || !pendingText.trim() || isPlacingAnnotation}
          onClick={handleStartPlacing}
        >
          {isPlacingAnnotation ? 'Click drawing to place pin…' : 'Add Pin Annotation'}
        </button>
      </div>
    </div>
  );
};
