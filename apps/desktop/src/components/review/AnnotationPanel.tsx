import React, { useState } from 'react';
import { useReviewStore } from '../../stores/reviewStore';

interface Annotation {
  id: string;
  content: string;
  author: string;
  severity: string;
  timestamp: string;
}

// Helper utility to parse ISO datetime strings from backend reliably as UTC
const parseUtcDate = (dateStr: string | null | undefined): Date => {
  if (!dateStr) return new Date();
  const utcStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  return new Date(utcStr);
};

export const AnnotationPanel: React.FC = () => {
  const { selectedViolationId } = useReviewStore();
  const [newAnnotation, setNewAnnotation] = useState('');
  
  // Mock loaded annotations
  const annotations: Annotation[] = [];

  const handleAddAnnotation = () => {
    if (!newAnnotation.trim()) return;
    // Dispatch to backend API
    setNewAnnotation('');
  };

  return (
    <div className="annotation-panel bg-bg-sidebar text-text-primary p-4 flex flex-col h-full border-l border-border-color" style={{ width: '300px' }}>
      <h2 className="text-lg font-bold border-b border-border-color pb-2 mb-4">Reviewer Annotations</h2>
      
      {selectedViolationId && (
        <div className="bg-red-500/10 text-red-500 p-2 rounded mb-4 text-xs border border-red-500/20">
          Linked to Violation: {selectedViolationId.substring(0, 8)}...
        </div>
      )}

      <div className="flex-1 overflow-y-auto space-y-3 mb-4">
        {annotations.length === 0 ? (
          <p className="text-text-muted text-sm text-center mt-10">No annotations added yet.</p>
        ) : (
          annotations.map(ann => (
            <div key={ann.id} className="bg-bg-card border border-border-color p-3 rounded text-sm">
              <div className="flex justify-between items-center mb-1">
                <span className="font-semibold text-accent-cyan">{ann.author}</span>
                <span className="text-xs text-text-muted">{parseUtcDate(ann.timestamp).toLocaleDateString()}</span>
              </div>
              <p className="text-text-secondary">{ann.content}</p>
            </div>
          ))
        )}
      </div>

      <div className="mt-auto">
        <textarea
          className="w-full bg-bg-card text-text-primary text-sm p-2 rounded border border-border-color focus:border-accent-cyan outline-none resize-none"
          rows={3}
          placeholder="Add engineering review notes..."
          value={newAnnotation}
          onChange={(e) => setNewAnnotation(e.target.value)}
        />
        <button 
          className="w-full bg-accent-cyan text-on-accent font-bold py-2 px-4 rounded mt-2 transition-colors cursor-pointer"
          onClick={handleAddAnnotation}
        >
          Add Pin Annotation
        </button>
      </div>
    </div>
  );
};
