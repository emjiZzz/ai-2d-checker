import React, { useState } from "react";
import { createPortal } from "react-dom";
import { useRoomStore } from "../../stores/roomStore";
import { useRooms } from "../../hooks/useRooms";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";

// The create form used to carry a four-way COMPARISON ENGINE picker behind a DEV badge.
// `rag_ai`, `ai_vision` and `hybrid` were removed (ADR-006), and a chooser with one option
// is not a choice — so the whole section is gone rather than reduced to a single button.
// `comparison_method` is no longer sent on create; the server defaults it to "deterministic".

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

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    try {
      const newRoom = await createRoom({ name, description, client_name: clientName });
      setIsCreating(false);
      setName("");
      setClientName("");
      setDescription("");
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
      <div className="flex-1 overflow-y-auto p-10 w-full bg-bg-dark min-h-full relative selection:bg-accent-cyan/30">
        <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-accent-cyan/5 rounded-full blur-[120px] pointer-events-none"></div>
        <div className="max-w-5xl mx-auto relative z-10">
          <div className="flex items-end justify-between mb-10 mt-4">
            <div>
              <h1 className="text-4xl font-black text-text-primary m-0 tracking-tight">Test Area</h1>
              <p className="text-sm text-text-muted mt-2 font-medium tracking-wide">Manage your audit rooms and test sessions.</p>
            </div>
            <Skeleton className="h-11 w-36 rounded-lg" />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="bg-bg-card border border-border-color rounded-2xl p-6 flex items-start gap-5">
                <Skeleton className="w-12 h-12 rounded-xl shrink-0" />
                <div className="flex-1 min-w-0 pt-1">
                  <Skeleton className="h-5 w-48 rounded-md mb-3" />
                  <Skeleton className="h-3 w-72 rounded-md mb-6" />
                  <div className="pt-4 border-t border-border-color flex gap-4">
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
    <div className="flex flex-col items-center justify-start flex-1 overflow-y-auto p-6 md:p-8 pb-12 w-full bg-bg-dark min-h-full relative selection:bg-accent-cyan/30">
      {/* Ambient background glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-[300px] bg-accent-cyan/[0.03] rounded-full blur-[140px] pointer-events-none"></div>

      <div className="w-full max-w-[1400px] relative z-10 flex flex-col flex-1 min-h-[calc(100vh-140px)]">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-5 mb-6 pb-5 border-b border-border-color/60">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-cyan/10 border border-accent-cyan/20 text-accent-cyan text-[11px] font-bold tracking-wider uppercase mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-pulse" />
              AI Compliance Workspaces
            </div>
            <h1 className="text-3xl md:text-4xl font-black text-text-primary m-0 tracking-tight">
              Test Rooms
            </h1>
            <p className="text-sm text-text-muted mt-1.5 font-medium leading-relaxed">
              Initialize CAD revision comparison sessions, assign reference drawings, and trigger automated AI compliance checks.
            </p>
          </div>
          {rooms.length > 0 && (
            <div className="flex items-center gap-3 shrink-0">
              <Button
                variant="primary"
                className="rounded-xl shadow-lg shadow-accent-cyan/20 hover:shadow-accent-cyan/30 transition-all font-bold text-xs sm:text-sm px-7 h-11 inline-flex items-center justify-center text-center gap-2 min-w-[160px]"
                onClick={() => setIsCreating(true)}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>
                <span className="text-center font-bold">Create Room</span>
              </Button>
            </div>
          )}
        </div>

        {/* ── Fully custom Create Room dialog ── */}
        {isCreating && createPortal(
          <div
            style={{
              position: "fixed", inset: 0, zIndex: 9999,
              display: "flex", alignItems: "center", justifyContent: "center",
              backgroundColor: "rgba(0,0,0,0.55)",
              backdropFilter: "blur(6px)",
              padding: "16px",
            }}
            onMouseDown={(e) => { if (e.target === e.currentTarget) setIsCreating(false); }}
          >
            <div style={{
              width: "100%", maxWidth: "560px",
              backgroundColor: "var(--bg-card)",
              borderRadius: "24px",
              boxShadow: "0 25px 60px rgba(0,0,0,0.25)",
              overflow: "hidden",
              display: "flex", flexDirection: "column",
              maxHeight: "90vh",
            }}>
              {/* Header */}
              <div style={{ display: "flex", alignItems: "flex-start", gap: "16px", padding: "28px 32px 24px", borderBottom: "1px solid var(--border-color)" }}>
                <div style={{
                  width: 56, height: 56, borderRadius: 16, flexShrink: 0,
                  background: "linear-gradient(135deg, #7c3aed, #6d28d9)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  boxShadow: "0 8px 20px rgba(124,58,237,0.35)",
                }}>
                  <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                    <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
                    <line x1="12" y1="22.08" x2="12" y2="12"></line>
                  </svg>
                </div>
                <div style={{ flex: 1 }}>
                  <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "var(--text-primary)", lineHeight: 1.2 }}>Initialize New Room</h2>
                  <p style={{ margin: "4px 0 0", fontSize: 14, color: "var(--text-muted)", fontWeight: 400 }}>Set up a comparison workspace</p>
                </div>
                <button
                  onClick={() => setIsCreating(false)}
                  style={{ background: "none", border: "none", cursor: "pointer", padding: 6, borderRadius: 8, color: "var(--text-muted)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}
                  aria-label="Close"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              </div>

              {/* Body */}
              <form id="create-room-form" onSubmit={handleCreate} style={{ padding: "28px 32px", display: "flex", flexDirection: "column", gap: 20, overflowY: "auto" }}>
                {/* Room Name */}
                <div>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: 10 }}>
                    ROOM NAME <span style={{ color: "#ef4444" }}>*</span>
                  </label>
                  <input
                    autoFocus
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Architectural Phase 1 vs Phase 2"
                    required
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "var(--bg-dark)", border: "1.5px solid var(--border-color)",
                      borderRadius: 16, padding: "14px 20px",
                      fontSize: 14, color: "var(--text-primary)",
                      outline: "none", transition: "border-color 0.15s",
                    }}
                    onFocus={(e) => { e.target.style.borderColor = "#7c3aed"; e.target.style.boxShadow = "0 0 0 3px rgba(124,58,237,0.12)"; }}
                    onBlur={(e) => { e.target.style.borderColor = "var(--border-color)"; e.target.style.boxShadow = "none"; }}
                  />
                </div>

                {/* Client */}
                <div>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: 10 }}>
                    CLIENT <span style={{ fontSize: 11, fontWeight: 400, textTransform: "none", letterSpacing: 0, color: "var(--text-muted)" }}>optional</span>
                  </label>
                  <input
                    type="text"
                    value={clientName}
                    onChange={(e) => setClientName(e.target.value)}
                    placeholder="e.g. Acme Corp"
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "var(--bg-dark)", border: "1.5px solid var(--border-color)",
                      borderRadius: 16, padding: "14px 20px",
                      fontSize: 14, color: "var(--text-primary)",
                      outline: "none", transition: "border-color 0.15s",
                    }}
                    onFocus={(e) => { e.target.style.borderColor = "#7c3aed"; e.target.style.boxShadow = "0 0 0 3px rgba(124,58,237,0.12)"; }}
                    onBlur={(e) => { e.target.style.borderColor = "var(--border-color)"; e.target.style.boxShadow = "none"; }}
                  />
                </div>

                {/* Description */}
                <div>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: 10 }}>
                    DESCRIPTION <span style={{ fontSize: 11, fontWeight: 400, textTransform: "none", letterSpacing: 0, color: "var(--text-muted)" }}>optional</span>
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Add notes, context, or goals for this testing session..."
                    rows={4}
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "var(--bg-dark)", border: "1.5px solid var(--border-color)",
                      borderRadius: 16, padding: "14px 20px",
                      fontSize: 14, color: "var(--text-primary)",
                      outline: "none", resize: "none", transition: "border-color 0.15s",
                      fontFamily: "inherit",
                    }}
                    onFocus={(e) => { e.target.style.borderColor = "#7c3aed"; e.target.style.boxShadow = "0 0 0 3px rgba(124,58,237,0.12)"; }}
                    onBlur={(e) => { e.target.style.borderColor = "var(--border-color)"; e.target.style.boxShadow = "none"; }}
                  />
                </div>

              </form>

              {/* Footer */}
              <div style={{ padding: "20px 32px", borderTop: "1px solid var(--border-color)", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 12 }}>
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  style={{ background: "none", border: "none", cursor: "pointer", fontSize: 15, fontWeight: 600, color: "var(--text-muted)", padding: "10px 20px", borderRadius: 12 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  form="create-room-form"
                  disabled={!name.trim()}
                  style={{
                    background: name.trim() ? "linear-gradient(135deg, #7c3aed, #6d28d9)" : "var(--border-color)",
                    color: "#ffffff",
                    border: "none", cursor: name.trim() ? "pointer" : "not-allowed",
                    fontSize: 15, fontWeight: 700,
                    padding: "12px 28px",
                    borderRadius: 99,
                    boxShadow: name.trim() ? "0 4px 16px rgba(124,58,237,0.35)" : "none",
                    display: "flex", alignItems: "center", gap: 8,
                    transition: "all 0.15s",
                  }}
                >
                  Create &amp; Open
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12h14" /><path d="m12 5 7 7-7 7" />
                  </svg>
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}

        {/* FULL WIDTH SPACIOUS INTEGRATED EMPTY STATE */}
        {!isCreating && rooms.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center w-full animate-in fade-in duration-500 min-h-[calc(100vh-220px)] py-10">
            {/* Centered Hero Graphic & Intro Text */}
            <div className="flex flex-col items-center justify-center text-center">
              <div className="relative mb-5">
                <div className="w-20 h-20 rounded-3xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center shadow-xl shadow-accent-cyan/15 relative">
                  <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-accent-cyan">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                    <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
                    <line x1="12" y1="22.08" x2="12" y2="12"></line>
                  </svg>
                </div>
              </div>

              <h2 className="text-3xl lg:text-4xl font-black text-text-primary mb-3 tracking-tight">
                No Test Rooms Created Yet
              </h2>
              <p className="text-base lg:text-lg text-text-muted max-w-xl leading-relaxed font-medium mb-7">
                Create a workspace room to upload reference and revision drawings (DWG, DXF, STEP, PDF) and execute AI compliance checks.
              </p>

              {/* Centered Primary Call to Action Button */}
              <Button
                variant="primary"
                onClick={() => setIsCreating(true)}
                className="rounded-xl shadow-lg shadow-accent-cyan/25 hover:shadow-accent-cyan/40 transition-all font-extrabold px-10 h-12 text-sm sm:text-base inline-flex items-center justify-center text-center gap-2.5 min-w-[180px] cursor-pointer hover:-translate-y-0.5"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>
                <span className="text-center font-extrabold">Create Room</span>
              </Button>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-4 w-full pb-16">
          {rooms.map((room) => (
            <div
              key={room.id}
              onClick={() => openRoom(room.id)}
              className="group relative bg-bg-card border border-border-color hover:bg-sidebar-item-hover hover:border-accent-cyan/30 rounded-2xl p-5 cursor-pointer transition-all duration-500 ease-out hover:-translate-y-1 hover:shadow-[0_16px_40px_-12px_rgba(34,211,238,0.2)] flex flex-col sm:flex-row items-center gap-5 backdrop-blur-md overflow-hidden animate-in fade-in slide-in-from-bottom-4 w-full"
            >
              {/* Subtle hover glow inside card */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-accent-cyan/10 blur-[80px] rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none"></div>

              {/* Icon block - shifted slightly right for visual centering */}
              <div className="ml-3 w-12 h-12 rounded-xl bg-bg-sidebar border border-border-color flex items-center justify-center shrink-0 shadow-inner group-hover:border-accent-cyan/30 transition-all duration-500">
                <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-text-muted group-hover:text-accent-cyan transition-colors duration-500">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <path d="M9 15h6"></path>
                  <path d="M9 11h6"></path>
                </svg>
              </div>

              {/* Main Content */}
              <div className="flex-1 min-w-0 flex flex-col justify-center">
                <div className="flex items-center gap-3 mb-1 flex-wrap">
                  <h3 className="text-lg font-bold text-text-primary transition-colors truncate tracking-tight">
                    {room.name}
                  </h3>
                  {room.client_name && (
                    <span className="inline-flex items-center text-xs font-bold text-accent-cyan bg-accent-cyan/10 px-3 py-1 rounded-full border border-accent-cyan/20 shrink-0 uppercase tracking-widest">
                      {room.client_name}
                    </span>
                  )}
                  {/* Unconditional: there is one engine, and a room that predates the field
                      runs it too, so gating on the value would hide the badge on old rooms. */}
                  <span className="inline-flex items-center text-xs font-bold text-emerald-500 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20 uppercase tracking-widest shrink-0">
                    Deterministic
                  </span>
                </div>

                <p className="text-sm text-text-muted transition-colors font-medium">
                  {room.description || "No description provided."}
                </p>

                {/* Drawings separated structurally */}
                {(room.active_old_drawing_name || room.active_new_drawing_name) && (
                  <div className="mt-4 pt-4 border-t border-border-color flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 w-full">

                    {/* Reference Drawing */}
                    <div className="flex flex-col gap-2 w-full sm:w-[45%] text-left">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted ml-1">Reference</span>
                      <div className="flex items-center gap-3 overflow-hidden bg-bg-dark px-4 py-3 rounded-xl border border-border-color">
                        <div className="w-7 h-7 rounded-md bg-bg-card flex items-center justify-center shrink-0 border border-border-color">
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-text-muted"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                        </div>
                        <span className="text-sm text-text-secondary truncate font-medium" title={room.active_old_drawing_name || "None"}>
                          {room.active_old_drawing_name || "Unassigned"}
                        </span>
                      </div>
                    </div>

                    {/* Connector */}
                    <div className="hidden sm:flex shrink-0 items-center justify-center w-8 self-end mb-4">
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-text-muted group-hover:text-accent-cyan transition-colors duration-500"><path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>
                    </div>

                    {/* Revision Drawing */}
                    <div className="flex flex-col gap-2 w-full sm:w-[45%] text-left">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-accent-cyan ml-1">Revision</span>
                      <div className="flex items-center gap-3 overflow-hidden bg-accent-cyan/5 px-4 py-3 rounded-xl border border-accent-cyan/20">
                        <div className="w-7 h-7 rounded-md bg-accent-cyan/10 flex items-center justify-center shrink-0">
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent-cyan"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                        </div>
                        <span className="text-sm text-accent-cyan truncate font-medium" title={room.active_new_drawing_name || "None"}>
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
                  className="text-text-muted hover:text-red-500 hover:bg-red-500/10 rounded-xl p-2.5 opacity-0 group-hover:opacity-100 transition-all duration-300 transform group-hover:scale-100 scale-90"
                  title="Delete Room"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
                </button>
                <div className="flex flex-col items-end gap-1 mt-auto">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">Last Opened</span>
                  <span className="text-xs text-text-muted font-medium">
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
