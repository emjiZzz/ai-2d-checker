import React, { useState, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import { Plus, X, Trash2, ArrowRight, FileText, Layers, ShieldCheck, FolderGit2, Search, ArrowUpDown, Clock } from "lucide-react";
import { useRoomStore, type RoomMode } from "../../stores/roomStore";
import { useRooms } from "../../hooks/useRooms";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { ConfirmModal } from "../../components/ui/ConfirmModal";
import { isPrototypeMode } from "../../config/features";

type StatusFilter = "all" | "ready" | "unassigned";
type SortOption = "recent" | "name" | "created";

const ITEMS_PER_PAGE = 12;

export const RoomsView: React.FC = () => {
  const { rooms, isLoading, createRoom, deleteRoom } = useRooms();
  const { openRoom } = useRoomStore();

  const [isCreating, setIsCreating] = useState(false);
  const [name, setName] = useState("");
  const [roomMode, setRoomMode] = useState<RoomMode>(isPrototypeMode() ? "manual_check" : "ai_comparison");

  // Deletion confirmation modal state
  const [deletingRoom, setDeletingRoom] = useState<{ id: string; name: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Search, Filter & Sort State
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortOption>("recent");
  const [displayLimit, setDisplayLimit] = useState(ITEMS_PER_PAGE);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Prototype isolation
  const baseRooms = useMemo(() => {
    return isPrototypeMode()
      ? rooms.filter((r) => r.room_mode === "manual_check")
      : rooms;
  }, [rooms]);

  // Global Keyboard Shortcut: '/' to focus search, 'Escape' to blur/clear
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isCreating) return;
      if (e.key === "/" && document.activeElement !== searchInputRef.current && !(document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        searchInputRef.current?.focus();
      } else if (e.key === "Escape" && document.activeElement === searchInputRef.current) {
        if (searchQuery) {
          setSearchQuery("");
        } else {
          searchInputRef.current?.blur();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isCreating, searchQuery]);

  // Filtered & Sorted Rooms Pipeline
  const filteredRooms = useMemo(() => {
    return baseRooms.filter((room) => {
      // 1. Search Query Filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = room.name.toLowerCase().includes(q);
        const matchesClient = room.client_name?.toLowerCase().includes(q);
        const matchesDesc = room.description?.toLowerCase().includes(q);
        const matchesOld = room.active_old_drawing_name?.toLowerCase().includes(q);
        const matchesNew = room.active_new_drawing_name?.toLowerCase().includes(q);
        if (!matchesName && !matchesClient && !matchesDesc && !matchesOld && !matchesNew) {
          return false;
        }
      }

      // 2. Status Filter
      if (statusFilter === "ready") {
        if (!room.active_old_drawing_name || !room.active_new_drawing_name) return false;
      } else if (statusFilter === "unassigned") {
        if (room.active_old_drawing_name && room.active_new_drawing_name) return false;
      }

      return true;
    }).sort((a, b) => {
      if (sortBy === "name") {
        return a.name.localeCompare(b.name);
      }
      if (sortBy === "created") {
        const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
        const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
        return timeB - timeA;
      }
      // default: "recent" (last_opened_at or updated_at)
      const timeA = a.last_opened_at ? new Date(a.last_opened_at).getTime() : (a.updated_at ? new Date(a.updated_at).getTime() : 0);
      const timeB = b.last_opened_at ? new Date(b.last_opened_at).getTime() : (b.updated_at ? new Date(b.updated_at).getTime() : 0);
      return timeB - timeA;
    });
  }, [baseRooms, searchQuery, statusFilter, sortBy]);

  // Reset pagination limit on filter/search change
  useEffect(() => {
    setDisplayLimit(ITEMS_PER_PAGE);
  }, [searchQuery, statusFilter, sortBy]);

  // Lazy Loading Sentinel (IntersectionObserver)
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && displayLimit < filteredRooms.length) {
          setDisplayLimit((prev) => Math.min(prev + ITEMS_PER_PAGE, filteredRooms.length));
        }
      },
      { threshold: 0.1, rootMargin: "200px" }
    );

    const currentSentinel = sentinelRef.current;
    if (currentSentinel) {
      observer.observe(currentSentinel);
    }
    return () => {
      if (currentSentinel) observer.unobserve(currentSentinel);
    };
  }, [displayLimit, filteredRooms.length]);

  const visibleRooms = useMemo(() => {
    return filteredRooms.slice(0, displayLimit);
  }, [filteredRooms, displayLimit]);

  // Counts for filter pills
  const counts = useMemo(() => {
    const readyCount = baseRooms.filter((r) => r.active_old_drawing_name && r.active_new_drawing_name).length;
    return {
      all: baseRooms.length,
      ready: readyCount,
      unassigned: baseRooms.length - readyCount,
    };
  }, [baseRooms]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    try {
      const newRoom = await createRoom({
        name: name.trim(),
        description: "",
        client_name: "",
        room_mode: isPrototypeMode() ? "manual_check" : roomMode
      });
      setIsCreating(false);
      setName("");
      setRoomMode(isPrototypeMode() ? "manual_check" : "ai_comparison");
      openRoom(newRoom.id);
    } catch {
      // rollback handled by useRooms
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingRoom) return;
    setIsDeleting(true);
    try {
      await deleteRoom(deletingRoom.id);
      setDeletingRoom(null);
    } catch {
      // rollback handled by useRooms
    } finally {
      setIsDeleting(false);
    }
  };

  if (isLoading && baseRooms.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto p-8 w-full bg-bg-dark min-h-full">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-end justify-between mb-8 pb-4 border-b border-border-color">
            <div>
              <Skeleton className="h-4 w-36 mb-2 rounded-none" />
              <Skeleton className="h-8 w-64 rounded-none" />
            </div>
            <Skeleton className="h-10 w-36 rounded-none" />
          </div>

          <div className="grid grid-cols-1 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-bg-card border border-border-color p-5 flex items-center gap-5 rounded-none">
                <Skeleton className="w-12 h-12 rounded-none shrink-0" />
                <div className="flex-1 min-w-0">
                  <Skeleton className="h-5 w-48 mb-2 rounded-none" />
                  <Skeleton className="h-3 w-72 rounded-none" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-start flex-1 overflow-y-auto p-6 md:p-10 pb-16 w-full bg-bg-dark min-h-full select-none">
      <div className="w-full max-w-6xl flex flex-col flex-1">

        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-6 border-b border-border-color">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-0.5 border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan text-[11px] font-mono font-bold tracking-wider uppercase mb-2 rounded-none">
              <ShieldCheck size={13} className="text-accent-cyan" />
              {isPrototypeMode() ? "CAD Ground Truth Workspaces" : "AI Compliance Workspaces"}
            </div>
            <h1 className="text-2xl md:text-3xl font-black font-mono text-text-primary m-0 tracking-tight uppercase">
              {isPrototypeMode() ? "Inspection Rooms" : "Test Rooms"}
            </h1>
            <p className="text-xs md:text-sm text-text-muted mt-1 font-sans">
              {isPrototypeMode()
                ? "Manage 2D CAD inspection rooms, link reference and revision drawing pairs, and record ground truth discrepancy markings."
                : "Initialize CAD revision comparison sessions, assign reference drawings, and trigger automated AI compliance checks."}
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <Button
              variant="primary"
              className="rounded-none font-mono font-bold text-xs px-6 h-10 inline-flex items-center justify-center gap-2 cursor-pointer transition-all uppercase tracking-wider"
              onClick={() => setIsCreating(true)}
            >
              <Plus size={16} />
              <span>Create Room</span>
            </Button>
          </div>
        </div>

        {/* ── Search, Status Filters & Sort Controls ── */}
        {baseRooms.length > 0 && (
          <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3.5 mb-6 p-3 bg-bg-card border border-border-color">
            {/* Search Input */}
            <div className="relative flex-1 min-w-[240px]">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search rooms, drawings, clients... (Press '/' to focus)"
                className="w-full bg-bg-dark border border-border-color focus:border-accent-cyan pl-9 pr-8 py-1.5 text-xs text-text-primary outline-none rounded-none font-mono placeholder:text-text-muted/60 transition-colors"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary p-0.5 cursor-pointer"
                  title="Clear search"
                >
                  <X size={13} />
                </button>
              )}
            </div>

            {/* Filter Pills & Sort Select */}
            <div className="flex items-center gap-2 flex-wrap shrink-0">
              {/* Status Filter Buttons */}
              <div className="flex items-center border border-border-color bg-bg-dark p-0.5 text-xs font-mono">
                <button
                  onClick={() => setStatusFilter("all")}
                  className={`px-2.5 py-1 text-[11px] font-bold uppercase transition-colors cursor-pointer ${statusFilter === "all"
                    ? "bg-bg-card text-accent-cyan border border-border-color"
                    : "text-text-muted hover:text-text-primary"
                    }`}
                >
                  All ({counts.all})
                </button>
                <button
                  onClick={() => setStatusFilter("ready")}
                  className={`px-2.5 py-1 text-[11px] font-bold uppercase transition-colors cursor-pointer ${statusFilter === "ready"
                    ? "bg-bg-card text-emerald-400 border border-border-color"
                    : "text-text-muted hover:text-text-primary"
                    }`}
                >
                  Linked ({counts.ready})
                </button>
                <button
                  onClick={() => setStatusFilter("unassigned")}
                  className={`px-2.5 py-1 text-[11px] font-bold uppercase transition-colors cursor-pointer ${statusFilter === "unassigned"
                    ? "bg-bg-card text-amber-400 border border-border-color"
                    : "text-text-muted hover:text-text-primary"
                    }`}
                >
                  Draft ({counts.unassigned})
                </button>
              </div>

              {/* Sort Selector */}
              <div className="flex items-center gap-1.5 px-2.5 py-1 bg-bg-dark border border-border-color text-xs font-mono text-text-secondary">
                <ArrowUpDown size={12} className="text-text-muted" />
                <span className="text-[10px] text-text-muted uppercase">Sort:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as SortOption)}
                  className="bg-transparent text-xs text-text-primary font-mono outline-none cursor-pointer pr-1"
                >
                  <option value="recent" className="bg-bg-card text-text-primary">Recently Opened</option>
                  <option value="name" className="bg-bg-card text-text-primary">Name (A–Z)</option>
                  <option value="created" className="bg-bg-card text-text-primary">Newest Created</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* ── Create Room Modal (Matches EngineerPromptModal Enterprise Layout) ── */}
        {isCreating && createPortal(
          <div
            className="fixed inset-0 z-[9999] flex items-center justify-center modal-backdrop p-6 animate-in fade-in duration-150 select-none"
            onMouseDown={(e) => { if (e.target === e.currentTarget) setIsCreating(false); }}
          >
            <div className="bg-bg-card border-2 border-border-color shadow-2xl w-full max-w-xl p-8 md:p-10 text-text-primary flex flex-col gap-6 relative rounded-none animate-in zoom-in-95 duration-150">
              {/* Top-Right Red Close Button */}
              <button
                onClick={() => setIsCreating(false)}
                className="absolute top-5 right-5 text-rose-500 hover:text-rose-600 hover:bg-rose-500/10 p-1.5 transition-colors cursor-pointer rounded-none"
                title="Close"
              >
                <X size={22} />
              </button>

              {/* Header */}
              <div className="flex items-center gap-4 border-b border-border-color pb-5">
                <div className="w-12 h-12 bg-accent-cyan/10 border border-accent-cyan/30 flex items-center justify-center text-accent-cyan shrink-0 rounded-none">
                  <FolderGit2 size={24} />
                </div>
                <div className="flex flex-col">
                  <h2 className="text-lg md:text-xl font-black tracking-wider uppercase text-text-primary font-mono">
                    Initialize Inspection Room
                  </h2>
                  <p className="text-sm text-text-muted mt-0.5">
                    Set up drawing comparison &amp; ground-truth workspace
                  </p>
                </div>
              </div>

              {/* Body */}
              <form id="create-room-form" onSubmit={handleCreate} className="flex flex-col gap-6">
                {/* Room Name */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs md:text-sm font-bold uppercase tracking-wider text-text-secondary font-mono">
                      Room Name / DWG No.
                    </label>
                    <span className="text-xs font-normal text-accent-cyan uppercase tracking-wider font-mono">
                      Required
                    </span>
                  </div>

                  <input
                    autoFocus
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter room name or dwg no."
                    required
                    className="w-full bg-transparent border border-border-color px-4 py-3.5 text-sm md:text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-text-primary transition-colors rounded-none font-medium"
                  />
                  <p className="text-xs text-text-muted mt-0.5">
                    Give this evaluation session a clean name to organize your CAD drawing pair.
                  </p>
                </div>

                {/* Centered Large PROCEED Button */}
                <div className="flex items-center justify-center pt-2">
                  <Button
                    variant="primary"
                    type="submit"
                    form="create-room-form"
                    disabled={!name.trim()}
                    className="rounded-none font-mono font-bold text-sm tracking-wider uppercase w-full max-w-[240px] py-3.5 flex items-center justify-center gap-2 cursor-pointer shadow-lg shadow-accent-cyan/15 hover:shadow-accent-cyan/25"
                  >
                    <span>CREATE &amp; OPEN</span>
                    <ArrowRight size={16} />
                  </Button>
                </div>
              </form>
            </div>
          </div>,
          document.body
        )}

        {/* Global Empty State (Zero Rooms created yet) */}
        {!isCreating && baseRooms.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center w-full py-16 text-center border-2 border-dashed border-border-color bg-bg-card/40 my-4">
            <div className="w-16 h-16 bg-accent-cyan/10 border border-accent-cyan/30 flex items-center justify-center text-accent-cyan mb-4 rounded-none">
              <Layers size={32} />
            </div>
            <h2 className="text-xl font-mono font-bold text-text-primary uppercase tracking-wide mb-2">
              No Inspection Rooms Created Yet
            </h2>
            <p className="text-xs md:text-sm text-text-muted max-w-md mb-6 leading-relaxed">
              Create your first inspection room to load CAD drawing pairs (DXF, DWG) and record ground truth markings.
            </p>
            <Button
              variant="primary"
              onClick={() => setIsCreating(true)}
              className="rounded-none font-mono font-bold text-xs px-6 h-10 inline-flex items-center gap-2 uppercase tracking-wider cursor-pointer"
            >
              <Plus size={16} />
              <span>Create Inspection Room</span>
            </Button>
          </div>
        )}

        {/* Search / Filter Zero Results State */}
        {!isCreating && baseRooms.length > 0 && filteredRooms.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center w-full py-12 text-center border border-border-color bg-bg-card/30 my-4">
            <Search size={28} className="text-text-muted mb-3" />
            <h3 className="text-sm font-mono font-bold text-text-primary uppercase tracking-wide mb-1">
              No Matching Rooms Found
            </h3>
            <p className="text-xs text-text-muted max-w-sm mb-4">
              No inspection rooms match "{searchQuery}" with the current filters.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSearchQuery("");
                setStatusFilter("all");
              }}
              className="rounded-none font-mono text-xs uppercase"
            >
              Clear Filters
            </Button>
          </div>
        )}

        {/* Rooms Grid / List */}
        {visibleRooms.length > 0 && (
          <div className="flex flex-col gap-3.5 w-full">
            <div className="flex items-center justify-between text-[11px] font-mono text-text-muted px-1">
              <span>Showing {visibleRooms.length} of {filteredRooms.length} room{filteredRooms.length === 1 ? "" : "s"}</span>
            </div>

            <div className="grid grid-cols-1 gap-3 w-full">
              {visibleRooms.map((room) => (
                <div
                  key={room.id}
                  onClick={() => openRoom(room.id)}
                  className="group bg-bg-card border border-border-color hover:border-accent-cyan/60 rounded-none p-5 cursor-pointer transition-all duration-150 flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  {/* Left Column: Icon & Room Info */}
                  <div className="flex items-start gap-4 flex-1 min-w-0">
                    <div className="w-10 h-10 bg-bg-sidebar border border-border-color group-hover:border-accent-cyan/40 flex items-center justify-center shrink-0 text-text-muted group-hover:text-accent-cyan transition-colors">
                      <FileText size={20} />
                    </div>

                    <div className="flex flex-col flex-1 min-w-0">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <h3 className="text-sm md:text-base font-bold font-mono text-text-primary group-hover:text-accent-cyan transition-colors truncate">
                          {room.name}
                        </h3>

                        {room.client_name && (
                          <span className="text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan">
                            {room.client_name}
                          </span>
                        )}
                      </div>



                      {/* Drawing Pair Summary (if drawings loaded) */}
                      {(room.active_old_drawing_name || room.active_new_drawing_name) && (
                        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border-color/60 text-xs font-mono">
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-bg-dark border border-border-color text-text-secondary max-w-[220px] truncate">
                            <span className="text-[10px] text-text-muted uppercase">REF:</span>
                            <span className="truncate">{room.active_old_drawing_name || "Unassigned"}</span>
                          </div>
                          <span className="text-text-muted text-xs">➔</span>
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-accent-cyan/5 border border-accent-cyan/20 text-accent-cyan max-w-[220px] truncate">
                            <span className="text-[10px] text-accent-cyan/70 uppercase">REV:</span>
                            <span className="truncate font-bold">{room.active_new_drawing_name || "Unassigned"}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right Column: Timestamps & Actions */}
                  <div className="flex md:flex-col items-center md:items-end justify-between w-full md:w-auto shrink-0 pt-2 md:pt-0 border-t md:border-t-0 border-border-color/50 gap-2">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingRoom({ id: room.id, name: room.name });
                        }}
                        className="p-1.5 text-text-muted hover:text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/30 transition-colors cursor-pointer"
                        title="Delete Room"
                      >
                        <Trash2 size={15} />
                      </button>
                      <div className="flex items-center gap-1 text-xs font-mono font-bold text-accent-cyan opacity-0 group-hover:opacity-100 transition-opacity">
                        <span>Open</span>
                        <ArrowRight size={14} />
                      </div>
                    </div>

                    <div className="flex items-center gap-1 text-[11px] font-mono text-text-muted">
                      <Clock size={11} />
                      <span>
                        {room.last_opened_at
                          ? `Opened ${new Date(room.last_opened_at).toLocaleDateString()}`
                          : (room.created_at ? `Created ${new Date(room.created_at).toLocaleDateString()}` : "New")}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Lazy Loading Sentinel Element */}
            {displayLimit < filteredRooms.length && (
              <div ref={sentinelRef} className="py-6 flex items-center justify-center text-xs font-mono text-text-muted">
                <div className="w-4 h-4 border-2 border-accent-cyan border-t-transparent animate-spin mr-2" />
                <span>Loading more rooms...</span>
              </div>
            )}
          </div>
        )}

        {/* ── Global Confirmation Modal for Deletions ── */}
        <ConfirmModal
          isOpen={!!deletingRoom}
          onClose={() => !isDeleting && setDeletingRoom(null)}
          onConfirm={handleConfirmDelete}
          title="Delete Inspection Room"
          message={
            <div className="flex flex-col gap-2">
              <p>
                Are you sure you want to delete <span className="font-mono font-bold text-text-primary">"{deletingRoom?.name}"</span>?
              </p>
              <p className="text-xs text-text-muted">
                All associated CAD drawing pairs, ground truth markings, and review history in this room will be permanently removed.
              </p>
            </div>
          }
          confirmText="DELETE ROOM"
          cancelText="CANCEL"
          variant="danger"
          isLoading={isDeleting}
        />

      </div>
    </div>
  );
};
