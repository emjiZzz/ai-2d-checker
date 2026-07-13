import React, { useEffect, useState } from "react";
import { X, Search, File, Loader, AlertCircle } from "lucide-react";
import { DrawingItem, useWorkspaceStore } from "../../stores/workspaceStore";
import { useConnectionStore } from "../../stores/connectionStore";
import { useAuthStore } from "../../stores/authStore";
import { Button } from "../ui/Button";
import { fetchWithAuth } from "../../services/fetchUtils";

interface DrawingLibraryPickerProps {
  side: "old" | "new";
  onClose: () => void;
}

export const DrawingLibraryPicker: React.FC<DrawingLibraryPickerProps> = ({ side, onClose }) => {
  const [drawings, setDrawings] = useState<DrawingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const backendUrl = useConnectionStore((s) => s.backendUrl);
  const apiToken = useConnectionStore((s) => s.apiToken);
  const sessionToken = useAuthStore((s) => s.sessionToken);
  
  const selectDrawingFromLibrary = useWorkspaceStore(s => s.selectDrawingFromLibrary);

  useEffect(() => {
    const fetchDrawings = async () => {
      try {
        const res = await fetchWithAuth("/api/v1/drawings");
        if (!res.ok) throw new Error("Failed to fetch library drawings");
        const data = await res.json();
        if (data.success && Array.isArray(data.data)) {
          setDrawings(data.data);
        }
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchDrawings();
  }, [backendUrl, apiToken, sessionToken]);

  const handleSelect = async (drawing: DrawingItem) => {
    if (drawing.status !== "completed") return;
    await selectDrawingFromLibrary(drawing, side);
    onClose();
  };

  const filtered = drawings.filter(d => d.file_name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div 
        className="bg-bg-sidebar border border-border-color rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden animate-fade-in"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-border-color bg-bg-dark">
          <h2 className="text-lg font-bold text-text-primary">Select Drawing from Library</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X size={20} />
          </Button>
        </div>
        
        <div className="p-4 border-b border-border-color bg-bg-sidebar">
          <div className="relative">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input 
              type="text"
              placeholder="Search by filename..."
              className="w-full bg-bg-dark border border-border-color rounded-lg py-2 pl-10 pr-4 text-sm text-text-primary focus:outline-none focus:border-accent-cyan transition-colors"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 text-text-muted">
              <Loader className="spin-animation mb-3" size={24} />
              <span>Loading library...</span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12 text-red-400">
              <AlertCircle className="mb-3" size={24} />
              <span>{error}</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-text-muted">
              <File className="mb-3 opacity-30" size={32} />
              <span>No drawings found matching "{search}"</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-2 p-2">
              {filtered.map(drawing => {
                const isReady = drawing.status === "completed";
                return (
                  <div 
                    key={drawing.id}
                    onClick={() => handleSelect(drawing)}
                    className={`flex items-center gap-4 p-3 rounded-lg border transition-all ${
                      isReady 
                        ? "border-border-color bg-bg-dark hover:border-accent-cyan hover:bg-accent-cyan/5 cursor-pointer" 
                        : "border-border-color/50 bg-bg-dark/50 opacity-60 cursor-not-allowed"
                    }`}
                  >
                    <div className={`w-10 h-10 rounded flex items-center justify-center shrink-0 ${isReady ? "bg-accent-cyan/10 text-accent-cyan" : "bg-zinc-800 text-zinc-500"}`}>
                      <File size={20} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-text-primary truncate">{drawing.file_name}</div>
                      <div className="text-xs text-text-muted flex gap-3 mt-1">
                        <span>{new Date(drawing.created_at).toLocaleDateString()}</span>
                        <span>{drawing.format?.toUpperCase()}</span>
                      </div>
                    </div>
                    <div className="shrink-0 text-xs font-bold uppercase">
                      {isReady ? (
                        <span className="text-emerald-400">Ready</span>
                      ) : (
                        <span className="text-orange-400 flex items-center gap-1.5"><Loader size={12} className="spin-animation" /> Processing</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
