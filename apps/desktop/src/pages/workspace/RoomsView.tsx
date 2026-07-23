import React, { useState } from "react";
import { useRoomStore } from "../../stores/roomStore";
import { useRooms } from "../../hooks/useRooms";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { Modal } from "../../components/ui/Modal";

type ComparisonMethod = "rag" | "rag_ai" | "ai_vision" | "hybrid";

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
  const [comparisonMethod, setComparisonMethod] = useState<ComparisonMethod>("rag");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    try {
      const newRoom = await createRoom({ name, description, client_name: clientName, comparison_method: comparisonMethod });
      setIsCreating(false);
      setName("");
      setClientName("");
      setDescription("");
      setComparisonMethod("rag");
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
      <div className="flex-1 overflow-y-auto p-10 w-full bg-[#0a0a0a] min-h-full relative selection:bg-accent-cyan/30">
        <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-accent-cyan/5 rounded-full blur-[120px] pointer-events-none"></div>
        <div className="max-w-5xl mx-auto relative z-10">
          <div className="flex items-end justify-between mb-10 mt-4">
            <div>
              <h1 className="text-4xl font-black text-white/90 m-0 tracking-tight">Test Area</h1>
              <p className="text-sm text-white/40 mt-2 font-medium tracking-wide">Manage your audit rooms and test sessions.</p>
            </div>
            <Skeleton className="h-11 w-36 rounded-lg" />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="bg-white/[0.02] border border-white/5 rounded-2xl p-6 flex items-start gap-5">
                <Skeleton className="w-12 h-12 rounded-xl shrink-0" />
                <div className="flex-1 min-w-0 pt-1">
                  <Skeleton className="h-5 w-48 rounded-md mb-3" />
                  <Skeleton className="h-3 w-72 rounded-md mb-6" />
                  <div className="pt-4 border-t border-white/5 flex gap-4">
                    <Skeleton className="h-6 w-full rounded-md" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-start flex-1 overflow-y-auto p-10 w-full bg-[#0a0a0a] min-h-full relative selection:bg-accent-cyan/30">
      {/* Ambient background glow */}
      <div className="absolute top-0 w-[600px] h-[600px] bg-accent-cyan/[0.03] rounded-full blur-[120px] pointer-events-none"></div>

      <div className="w-full max-w-4xl relative z-10 flex flex-col pt-10">
        <div className="flex items-center justify-between mb-16">
          <div>
            <h1 className="text-4xl font-black bg-gradient-to-br from-white via-white/90 to-white/40 bg-clip-text text-transparent m-0 tracking-tight">
              Test Rooms
            </h1>
            <p className="text-sm text-white/40 mt-2 font-medium tracking-wide">
              Manage your test rooms and sessions.
            </p>
          </div>
          {rooms.length > 0 && (
            <Button
              variant="primary"
              size="lg"
              className="rounded-xl shadow-lg shadow-accent-cyan/20 hover:shadow-accent-cyan/30 transition-all font-bold px-8 py-4"
              onClick={() => setIsCreating(true)}
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
            <div className="w-10 h-10 bg-accent-cyan/10 rounded-xl flex items-center justify-center border border-accent-cyan/20">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-accent-cyan"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
            </div>
          }
          maxWidthClassName="max-w-xl"
          footer={
            <div className="flex items-center justify-end gap-3 w-full">
              <Button type="button" variant="ghost" size="lg" onClick={() => setIsCreating(false)}>
                Cancel
              </Button>
              <Button type="submit" form="create-room-form" variant="primary" size="lg" disabled={!name.trim()} className="min-w-[140px] rounded-xl font-bold shadow-lg shadow-accent-cyan/20">
                Create &amp; Open
              </Button>
            </div>
          }
        >
          <form id="create-room-form" onSubmit={handleCreate}>
            <div className="mb-6">
              <label className="block text-sm font-semibold text-white/80 mb-2">Room Name <span className="text-red-400">*</span></label>
              <input
                autoFocus
                type="text"
                className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-3.5 text-white/90 placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-accent-cyan/50 focus:border-transparent transition-all shadow-inner"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Architectural Phase 1 vs Phase 2"
                required
              />
            </div>
            <div className="mb-6">
              <label className="block text-sm font-semibold text-white/80 mb-2">Client (Optional)</label>
              <input
                type="text"
                className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-3.5 text-white/90 placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-accent-cyan/50 focus:border-transparent transition-all shadow-inner"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                placeholder="e.g. Acme Corp"
              />
            </div>
            <div className="mb-6">
              <label className="block text-sm font-semibold text-white/80 mb-2">Description (Optional)</label>
              <textarea
                className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-3.5 text-white/90 placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-accent-cyan/50 focus:border-transparent transition-all resize-none shadow-inner"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Add notes, context, or goals for this testing session..."
                rows={3}
              />
            </div>

            {/* ── Comparison Method Selector (dev benchmarking feature — visible to all users) ── */}
            <div className="bg-[#111]/50 border border-white/5 rounded-2xl p-5">
              <label className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
                Comparison Engine
                <span className="text-[9px] font-bold uppercase tracking-widest text-amber-400 bg-amber-400/10 border border-amber-400/20 px-1.5 py-0.5 rounded">
                  DEV
                </span>
              </label>
              <div className="grid grid-cols-4 gap-2 bg-[#1a1a1a] p-1.5 rounded-xl border border-white/5">
                <button
                  type="button"
                  id="method-rag"
                  onClick={() => setComparisonMethod("rag")}
                  className={`px-3 py-3 rounded-lg text-sm font-semibold transition-all ${comparisonMethod === "rag"
                    ? "bg-[#2a2a2a] text-white shadow-md border border-white/10"
                    : "text-white/40 hover:text-white/70 hover:bg-white/5 border border-transparent"
                    }`}
                >
                  <div className="flex items-center gap-1.5 justify-center mb-1">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                    RAG
                  </div>
                  <div className="text-[10px] font-medium opacity-60 leading-tight">SpatialDiffer + BOM</div>
                </button>
                <button
                  type="button"
                  id="method-rag-ai"
                  onClick={() => setComparisonMethod("rag_ai")}
                  className={`px-3 py-3 rounded-lg text-sm font-semibold transition-all ${comparisonMethod === "rag_ai"
                    ? "bg-[#2a2a2a] text-white shadow-md border border-white/10"
                    : "text-white/40 hover:text-white/70 hover:bg-white/5 border border-transparent"
                    }`}
                >
                  <div className="flex items-center gap-1.5 justify-center mb-1">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 8v4l3 3"></path></svg>
                    RAG + AI
                  </div>
                  <div className="text-[10px] font-medium opacity-60 leading-tight">Gemini (PNG+JSON)</div>
                </button>
                <button
                  type="button"
                  id="method-ai-vision"
                  onClick={() => setComparisonMethod("ai_vision")}
                  className={`px-3 py-3 rounded-lg text-sm font-semibold transition-all ${comparisonMethod === "ai_vision"
                    ? "bg-[#2a2a2a] text-white shadow-md border border-white/10"
                    : "text-white/40 hover:text-white/70 hover:bg-white/5 border border-transparent"
                    }`}
                >
                  <div className="flex items-center gap-1.5 justify-center mb-1">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                    AI VISION
                  </div>
                  <div className="text-[10px] font-medium opacity-60 leading-tight">Gemini (PNG Only)</div>
                </button>
                <button
                  type="button"
                  id="method-hybrid"
                  onClick={() => setComparisonMethod("hybrid")}
                  className={`px-3 py-3 rounded-lg text-sm font-semibold transition-all ${comparisonMethod === "hybrid"
                    ? "bg-[#2a2a2a] text-white shadow-md border border-white/10"
                    : "text-white/40 hover:text-white/70 hover:bg-white/5 border border-transparent"
                    }`}
                >
                  <div className="flex items-center gap-1.5 justify-center mb-1">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 11l3 3L22 4"></path><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
                    HYBRID
                  </div>
                  <div className="text-[10px] font-medium opacity-60 leading-tight">2 gens + verify</div>
                </button>
              </div>
            </div>
          </form>
        </Modal>

        {!isCreating && rooms.length === 0 && (
          <div className="flex flex-col items-center justify-center h-[55vh] animate-in fade-in duration-1000 zoom-in-95">
            <div className="relative mb-10">
              <div className="absolute inset-0 bg-accent-cyan/20 rounded-full blur-3xl animate-pulse"></div>
              <div className="relative w-32 h-32 bg-white/[0.02] rounded-[2rem] rotate-3 flex items-center justify-center shadow-[0_16px_40px_rgb(0,0,0,0.2)] border border-white/10 backdrop-blur-xl">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="text-accent-cyan -rotate-3"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
              </div>
            </div>
            <h3 className="text-2xl font-black text-white mb-3 tracking-tight">No Rooms Yet</h3>
            <p className="text-white/40 mb-10 max-w-sm text-center text-base leading-relaxed">
              Create your first room to assign drawings and run intelligent compliance audits.
            </p>
            <Button
              variant="primary"
              size="lg"
              onClick={() => setIsCreating(true)}
              className="hover:-translate-y-1 transition-all duration-300 shadow-xl shadow-accent-cyan/20 font-bold px-8 py-6 rounded-2xl text-lg"
            >
              + Create First Room
            </Button>
          </div>
        )}

        <div className="flex flex-col gap-8 w-full pb-16">
          {rooms.map((room) => (
            <div
              key={room.id}
              onClick={() => openRoom(room.id)}
              className="group relative bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] hover:border-accent-cyan/30 rounded-[2rem] p-8 cursor-pointer transition-all duration-500 ease-out hover:-translate-y-1 hover:shadow-[0_16px_40px_-12px_rgba(34,211,238,0.2)] flex flex-col sm:flex-row items-center gap-8 backdrop-blur-md overflow-hidden animate-in fade-in slide-in-from-bottom-4 w-full"
            >
              {/* Subtle hover glow inside card */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-accent-cyan/10 blur-[80px] rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none"></div>

              {/* Icon block - shifted slightly right for visual centering */}
              <div className="ml-6 w-16 h-16 rounded-2xl bg-gradient-to-br from-white/10 to-white/5 border border-white/10 flex items-center justify-center shrink-0 shadow-inner group-hover:from-accent-cyan/20 group-hover:to-accent-cyan/5 group-hover:border-accent-cyan/30 transition-all duration-500">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-white/50 group-hover:text-accent-cyan transition-colors duration-500">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <path d="M9 15h6"></path>
                  <path d="M9 11h6"></path>
                </svg>
              </div>

              {/* Main Content */}
              <div className="flex-1 min-w-0 flex flex-col justify-center">
                <div className="flex items-center gap-4 mb-2 flex-wrap">
                  <h3 className="text-2xl font-bold text-white/90 group-hover:text-white transition-colors truncate tracking-tight">
                    {room.name}
                  </h3>
                  {room.client_name && (
                    <span className="inline-flex items-center text-xs font-bold text-accent-cyan bg-accent-cyan/10 px-3 py-1 rounded-full border border-accent-cyan/20 shrink-0 uppercase tracking-widest">
                      {room.client_name}
                    </span>
                  )}
                  {room.comparison_method === "rag" && (
                    <span className="inline-flex items-center text-xs font-bold text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20 uppercase tracking-widest shrink-0">
                      RAG
                    </span>
                  )}
                  {room.comparison_method === "rag_ai" && (
                    <span className="inline-flex items-center text-xs font-bold text-violet-400 bg-violet-500/10 px-3 py-1 rounded-full border border-violet-500/20 uppercase tracking-widest shrink-0">
                      RAG + AI
                    </span>
                  )}
                  {room.comparison_method === "ai_vision" && (
                    <span className="inline-flex items-center text-xs font-bold text-fuchsia-400 bg-fuchsia-500/10 px-3 py-1 rounded-full border border-fuchsia-500/20 uppercase tracking-widest shrink-0">
                      AI VISION
                    </span>
                  )}
                  {room.comparison_method === "hybrid" && (
                    <span className="inline-flex items-center text-xs font-bold text-purple-400 bg-purple-500/10 px-3 py-1 rounded-full border border-purple-500/20 uppercase tracking-widest shrink-0">
                      HYBRID
                    </span>
                  )}
                </div>

                <p className="text-base text-white/40 group-hover:text-white/60 transition-colors font-medium">
                  {room.description || "No description provided."}
                </p>

                {/* Drawings separated structurally */}
                {(room.active_old_drawing_name || room.active_new_drawing_name) && (
                  <div className="mt-8 pt-6 border-t border-white/5 flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6 w-full">

                    {/* Reference Drawing */}
                    <div className="flex flex-col gap-2 w-full sm:w-[45%] text-left">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-white/30 ml-1">Reference</span>
                      <div className="flex items-center gap-3 overflow-hidden bg-black/20 px-4 py-3 rounded-xl border border-white/5">
                        <div className="w-7 h-7 rounded-md bg-white/10 flex items-center justify-center shrink-0">
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-white/60"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                        </div>
                        <span className="text-sm text-white/50 truncate font-medium" title={room.active_old_drawing_name || "None"}>
                          {room.active_old_drawing_name || "Unassigned"}
                        </span>
                      </div>
                    </div>

                    {/* Connector */}
                    <div className="hidden sm:flex shrink-0 items-center justify-center w-8 self-end mb-4">
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-white/10 group-hover:text-accent-cyan/50 transition-colors duration-500"><path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>
                    </div>

                    {/* Revision Drawing */}
                    <div className="flex flex-col gap-2 w-full sm:w-[45%] text-left">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-accent-cyan/50 ml-1">Revision</span>
                      <div className="flex items-center gap-3 overflow-hidden bg-accent-cyan/[0.03] px-4 py-3 rounded-xl border border-accent-cyan/10">
                        <div className="w-7 h-7 rounded-md bg-accent-cyan/10 flex items-center justify-center shrink-0">
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent-cyan/80"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                        </div>
                        <span className="text-sm text-accent-cyan/80 truncate font-medium" title={room.active_new_drawing_name || "None"}>
                          {room.active_new_drawing_name || "Unassigned"}
                        </span>
                      </div>
                    </div>

                  </div>
                )}
              </div>

              {/* Right Side Actions */}
              <div className="flex flex-col items-end justify-between self-stretch shrink-0 pl-2">
                <button
                  onClick={(e) => handleDelete(e, room.id)}
                  className="text-white/20 hover:text-red-400 hover:bg-red-400/10 rounded-xl p-2.5 opacity-0 group-hover:opacity-100 transition-all duration-300 transform group-hover:scale-100 scale-90"
                  title="Delete Room"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
                </button>
                <div className="flex flex-col items-end gap-1 mt-auto">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-white/20">Last Opened</span>
                  <span className="text-xs text-white/40 font-medium">
                    {room.last_opened_at ? new Date(room.last_opened_at).toLocaleDateString() : 'Never'}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
