import React, { useState } from "react";
import { useRoomStore } from "../../stores/roomStore";
import { useRooms } from "../../hooks/useRooms";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { Modal } from "../../components/ui/Modal";

type ComparisonMethod = "deterministic" | "full_ai" | "full_ai_vision";

export const RoomsView: React.FC = () => {
  // useRooms() owns the server state: list, loading, optimistic mutations.
  const { rooms, isLoading, createRoom, deleteRoom } = useRooms();

  // openRoom() stays in Zustand: it orchestrates a multi-step waterfall of
  // sequential API calls that hydrate workspaceStore — not a simple query.
  const { openRoom } = useRoomStore();

  const [isCreating, setIsCreating] = useState(false);

  // Form state (pure client state — correct home is useState, not the cache)
  const [name, setName] = useState("");
  const [clientName, setClientName] = useState("");
  const [description, setDescription] = useState("");
  const [comparisonMethod, setComparisonMethod] = useState<ComparisonMethod>("deterministic");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    try {
      const newRoom = await createRoom({ name, description, client_name: clientName, comparison_method: comparisonMethod });
      setIsCreating(false);
      setName("");
      setClientName("");
      setDescription("");
      setComparisonMethod("deterministic");
      // openRoom is a Zustand action that hydrates the workspace — called after
      // the Query mutation resolves so we have the real server-generated ID.
      openRoom(newRoom.id);
    } catch {
      // createRoom throws on failure; the optimistic row was already rolled back
      // by useRooms' onError handler, so no manual state cleanup needed here.
    }
  };

  const handleDelete = async (e: React.MouseEvent, roomId: string) => {
    e.stopPropagation();
    if (window.confirm("Are you sure you want to delete this room?")) {
      await deleteRoom(roomId);
    }
  };

  // isFetching (not isLoading) distinguishes a background SWR refetch from
  // an initial cold load. We only show the skeleton on first load.
  if (isLoading && rooms.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto p-10 w-full bg-bg-dark min-h-full">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-12">
            <div>
              <h1 className="text-4xl font-bold text-text-primary tracking-tight">Workspaces</h1>
              <p className="text-text-muted mt-2 text-lg">Manage your audit rooms and test sessions.</p>
            </div>
            <Skeleton className="h-12 w-36 rounded-md" />
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="bg-bg-card border border-border-color rounded-xl p-6 flex flex-col min-h-[220px]">
                <div className="flex justify-between items-start mb-4">
                  <Skeleton className="h-6 w-3/4 rounded-md" />
                </div>
                <Skeleton className="h-6 w-24 rounded-md mb-4" />
                <div className="space-y-2 mb-6 flex-1">
                  <Skeleton className="h-4 w-full rounded-md" />
                  <Skeleton className="h-4 w-5/6 rounded-md" />
                </div>
                <div className="mt-auto pt-4 border-t border-border-color flex items-center justify-between">
                  <Skeleton className="h-4 w-32 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-10 w-full bg-bg-dark min-h-full">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-12">
          <div>
            <h1 className="text-4xl font-bold text-text-primary tracking-tight">Workspaces</h1>
            <p className="text-text-muted mt-2 text-lg">Manage your audit rooms and test sessions.</p>
          </div>
          {rooms.length > 0 && (
            <Button 
              variant="primary"
              size="lg"
              onClick={() => setIsCreating(true)}
              className="shadow-[0_0_15px_rgba(37,99,235,0.3)] transition-all hover:-translate-y-0.5"
            >
              + Create Room
            </Button>
          )}
        </div>

        <Modal
          isOpen={isCreating}
          onClose={() => setIsCreating(false)}
          title="Initialize New Room"
          icon={
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-accent-cyan"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
          }
          maxWidthClassName="max-w-xl"
          footer={
            <div className="flex items-center justify-end gap-3">
              <Button
                type="button"
                variant="ghost"
                size="lg"
                onClick={() => setIsCreating(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                form="create-room-form"
                variant="primary"
                size="lg"
                disabled={!name.trim()}
                className="shadow-[0_0_15px_rgba(37,99,235,0.25)] min-w-[140px]"
              >
                Create &amp; Open
              </Button>
            </div>
          }
        >
            <form id="create-room-form" onSubmit={handleCreate}>
              <div className="mb-6">
                <label className="block text-sm font-medium text-text-secondary mb-2.5">Room Name <span className="text-red-400">*</span></label>
                <input
                  autoFocus
                  type="text"
                  className="w-full bg-bg-dark border border-border-color rounded-lg px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-cyan focus:border-transparent transition-all"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Architectural Phase 1 vs Phase 2"
                  required
                />
              </div>
              <div className="mb-6">
                <label className="block text-sm font-medium text-text-secondary mb-2.5">Client (Optional)</label>
                <input
                  type="text"
                  className="w-full bg-bg-dark border border-border-color rounded-lg px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-cyan focus:border-transparent transition-all"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  placeholder="e.g. Acme Corp"
                />
              </div>
              <div className="mb-6">
                <label className="block text-sm font-medium text-text-secondary mb-2.5">Description (Optional)</label>
                <textarea
                  className="w-full bg-bg-dark border border-border-color rounded-lg px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-cyan focus:border-transparent transition-all resize-none"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Add notes, context, or goals for this testing session..."
                  rows={3}
                />
              </div>

              {/* ── Comparison Method Selector (dev benchmarking feature — visible to all users) ── */}
              <div className="bg-bg-dark/60 border border-border-color rounded-xl p-4">
                <label className="text-sm font-medium text-text-secondary mb-3 flex items-center gap-2">
                  Comparison Method
                  <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400 bg-amber-400/10 border border-amber-400/30 px-1.5 py-0.5 rounded">
                    DEV
                  </span>
                </label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    id="method-deterministic"
                    onClick={() => setComparisonMethod("deterministic")}
                    className={`px-3 py-2.5 rounded-lg border text-sm font-medium transition-all ${
                      comparisonMethod === "deterministic"
                        ? "border-accent-cyan bg-accent-cyan/10 text-accent-cyan"
                        : "border-border-color bg-bg-card text-text-muted hover:border-text-muted"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 justify-center">
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                      Deterministic
                    </div>
                    <div className="text-[9px] mt-1 opacity-70 leading-tight">SpatialDiffer + BOMAnalyzer</div>
                  </button>
                  <button
                    type="button"
                    id="method-full-ai"
                    onClick={() => setComparisonMethod("full_ai")}
                    className={`px-3 py-2.5 rounded-lg border text-sm font-medium transition-all ${
                      comparisonMethod === "full_ai"
                        ? "border-violet-500 bg-violet-500/10 text-violet-400"
                        : "border-border-color bg-bg-card text-text-muted hover:border-text-muted"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 justify-center">
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 8v4l3 3"></path></svg>
                      Full AI
                    </div>
                    <div className="text-[9px] mt-1 opacity-70 leading-tight">Gemini (PNG + CAD JSON)</div>
                  </button>
                  <button
                    type="button"
                    id="method-full-ai-vision"
                    onClick={() => setComparisonMethod("full_ai_vision")}
                    className={`px-3 py-2.5 rounded-lg border text-sm font-medium transition-all ${
                      comparisonMethod === "full_ai_vision"
                        ? "border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-400"
                        : "border-border-color bg-bg-card text-text-muted hover:border-text-muted"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 justify-center">
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                      AI Vision
                    </div>
                    <div className="text-[9px] mt-1 opacity-70 leading-tight">Gemini (PNG Only)</div>
                  </button>
                </div>
                {comparisonMethod.startsWith("full_ai") && (
                  <p className="mt-3 text-xs text-amber-400/80 flex items-start gap-1.5">
                    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                    {comparisonMethod === "full_ai" 
                      ? "Full AI mode sends both drawing PNGs + full CAD context to Gemini."
                      : "Vision mode sends ONLY the drawing PNGs to Gemini, ignoring extracted CAD data."}
                    {" "}Results are for benchmarking only — use Deterministic for production.
                  </p>
                )}
              </div>

            </form>
        </Modal>

        {!isCreating && rooms.length === 0 && (
          <div className="flex flex-col items-center justify-center h-[50vh] animate-in fade-in duration-500">
            <div className="w-24 h-24 bg-bg-card rounded-full flex items-center justify-center mb-6 shadow-lg border border-border-color">
              <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="text-accent-cyan"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
            </div>
            <h3 className="text-3xl font-bold text-text-primary mb-4">No Rooms Yet</h3>
            <p className="text-text-muted mb-10 max-w-md text-center text-lg leading-relaxed">Create your first room to start comparing drawings and running AI compliance audits.</p>
            <Button 
              variant="primary"
              size="lg"
              onClick={() => setIsCreating(true)}
              className="px-8 py-6 text-lg shadow-[0_0_20px_rgba(37,99,235,0.2)] hover:shadow-[0_0_30px_rgba(37,99,235,0.4)] transition-all hover:-translate-y-1"
            >
              + Create First Room
            </Button>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {rooms.map((room) => (
            <div
              key={room.id}
              onClick={() => openRoom(room.id)}
              className="group bg-bg-card border border-border-color hover:border-accent-cyan/60 rounded-xl p-6 cursor-pointer transition-all duration-300 hover:shadow-lg flex flex-col min-h-[220px]"
            >
              <div className="flex justify-between items-start mb-4 relative">
                <h3 className="text-xl font-bold text-text-primary group-hover:text-accent-cyan transition-colors line-clamp-2 pr-8" title={room.name}>
                  {room.name}
                </h3>
                <button
                  onClick={(e) => handleDelete(e, room.id)}
                  className="text-text-muted hover:text-red-400 hover:bg-red-400/10 rounded-md p-1.5 opacity-0 group-hover:opacity-100 transition-all absolute -right-2 -top-2"
                  title="Delete Room"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 6h18"></path>
                    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
                  </svg>
                </button>
              </div>
              
              <div className="flex flex-wrap gap-2 mb-4">
                {room.client_name && (
                  <div className="inline-flex items-center text-xs font-medium text-accent-cyan bg-accent-cyan/10 px-2.5 py-1 rounded-md w-fit border border-accent-cyan/20">
                    <svg className="w-3.5 h-3.5 mr-1.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                    {room.client_name}
                  </div>
                )}
                {/* Method badge — always visible so devs can see at a glance */}
                {room.comparison_method === "full_ai" && (
                  <div className="inline-flex items-center text-xs font-bold text-violet-400 bg-violet-500/10 px-2.5 py-1 rounded-md w-fit border border-violet-500/20 uppercase tracking-wide">
                    <svg className="w-3 h-3 mr-1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 8v4l3 3"></path></svg>
                    Full AI
                  </div>
                )}
              </div>
              
              <p className="text-sm text-text-muted line-clamp-3 mb-6 flex-1 group-hover:text-text-secondary transition-colors">
                {room.description || "No description provided."}
              </p>
              
              <div className="mt-auto pt-4 border-t border-border-color flex items-center justify-between text-xs text-text-muted">
                <span className="flex items-center gap-1.5">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                  {room.last_opened_at ? new Date(room.last_opened_at).toLocaleDateString() : 'Never opened'}
                </span>
                
                <span className="text-accent-cyan opacity-0 group-hover:opacity-100 transition-opacity font-medium flex items-center gap-1">
                  Open <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
