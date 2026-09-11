import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  Plus,
  X,
  ArrowRight,
  Search,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight
} from "lucide-react";
import { useRoomStore, type RoomMode } from "../../stores/roomStore";
import { useRooms } from "../../hooks/useRooms";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { Modal } from "../../components/ui/Modal";
import { ConfirmModal } from "../../components/ui/ConfirmModal";
import { RealDrawingThumbnail, CadFileIcon } from "../../components/review/RealDrawingThumbnail";
import { isPrototypeMode } from "../../config/features";
import { useIsEngineerPromptBlocking } from "../../stores/engineerStore";

type SortOption = "recent" | "name" | "created";

// 4 columns x 3 rows = 12 slots max per page.
// Page 1 reserves 1 slot for "Create New" card + 11 room cards.
// Page 2+ displays 12 room cards.
export const ROOMS_ON_FIRST_PAGE = 11;
export const ROOMS_PER_PAGE = 12;

export const RoomsView: React.FC = () => {
  const { rooms, isLoading, createRoom, deleteRoom } = useRooms();
  const { openRoom } = useRoomStore();
  const { startTour } = useOnboardingStore();

  const [isCreating, setIsCreating] = useState(false);
  const [name, setName] = useState("");
  //: Why a create failed, shown in the dialog. Empty when there is nothing to report.
  const [createError, setCreateError] = useState("");
  const [roomMode, setRoomMode] = useState<RoomMode>(isPrototypeMode() ? "manual_check" : "ai_comparison");

  /**
   * Auto-launch the onboarding tour for first-time testers / users.
   */
  const engineerPromptBlocking = useIsEngineerPromptBlocking();
  useEffect(() => {
    if (engineerPromptBlocking) return;
    const hasSeen = localStorage.getItem("has_seen_interactive_tour");
    if (!hasSeen) {
      startTour();
    }
  }, [engineerPromptBlocking, startTour]);

  // Deletion confirmation modal state
  const [deletingRoom, setDeletingRoom] = useState<{ id: string; name: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Search, Sort & Pagination State
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortOption>("recent");
  const [currentPage, setCurrentPage] = useState(1);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Prototype isolation
  const baseRooms = useMemo(() => {
    return isPrototypeMode()
      ? rooms.filter((r) => r.room_mode === "manual_check")
      : rooms;
  }, [rooms]);

  // Global Keyboard Shortcut: '/' to focus search, 'Escape' to blur/clear
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isCreating || deletingRoom) return;
      if (
        e.key === "/" &&
        document.activeElement !== searchInputRef.current &&
        !(document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement)
      ) {
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
  }, [isCreating, deletingRoom, searchQuery]);

  // Filtered & Sorted Rooms Pipeline
  const filteredRooms = useMemo(() => {
    return baseRooms
      .filter((room) => {
        // Search Query Filter
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
        return true;
      })
      .sort((a, b) => {
        if (sortBy === "name") {
          return a.name.localeCompare(b.name);
        }
        if (sortBy === "created") {
          const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
          const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
          return timeB - timeA;
        }
        // default: "recent" (last_opened_at or updated_at)
        const timeA = a.last_opened_at
          ? new Date(a.last_opened_at).getTime()
          : a.updated_at
            ? new Date(a.updated_at).getTime()
            : 0;
        const timeB = b.last_opened_at
          ? new Date(b.last_opened_at).getTime()
          : b.updated_at
            ? new Date(b.updated_at).getTime()
            : 0;
        return timeB - timeA;
      });
  }, [baseRooms, searchQuery, sortBy]);

  // Total pages calculation (max 3 rows: 12 cards per page)
  const totalRooms = filteredRooms.length;
  const totalPages = Math.max(
    1,
    totalRooms <= ROOMS_ON_FIRST_PAGE
      ? 1
      : 1 + Math.ceil((totalRooms - ROOMS_ON_FIRST_PAGE) / ROOMS_PER_PAGE)
  );

  // Reset to page 1 on search or sort change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, sortBy]);

  // Clamp current page if total pages decreases
  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  // Sliced rooms for current page (max 3 rows rendered)
  const pageRooms = useMemo(() => {
    if (currentPage === 1) {
      return filteredRooms.slice(0, ROOMS_ON_FIRST_PAGE);
    }
    const startIndex = ROOMS_ON_FIRST_PAGE + (currentPage - 2) * ROOMS_PER_PAGE;
    return filteredRooms.slice(startIndex, startIndex + ROOMS_PER_PAGE);
  }, [filteredRooms, currentPage]);

  const handlePageChange = (newPage: number) => {
    const target = Math.max(1, Math.min(totalPages, newPage));
    setCurrentPage(target);
    if (typeof containerRef.current?.scrollTo === "function") {
      containerRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  // Keyboard pagination navigation (Left / Right arrow keys)
  useEffect(() => {
    const handlePageArrows = (e: KeyboardEvent) => {
      if (isCreating || deletingRoom) return;
      if (
        document.activeElement instanceof HTMLInputElement ||
        document.activeElement instanceof HTMLTextAreaElement ||
        document.activeElement instanceof HTMLSelectElement
      ) {
        return;
      }
      if (e.key === "ArrowLeft") {
        handlePageChange(currentPage - 1);
      } else if (e.key === "ArrowRight") {
        handlePageChange(currentPage + 1);
      }
    };
    window.addEventListener("keydown", handlePageArrows);
    return () => window.removeEventListener("keydown", handlePageArrows);
  }, [isCreating, deletingRoom, currentPage, totalPages]);

  // Text for item count display
  const itemRangeText = useMemo(() => {
    if (totalRooms === 0) return "0 workspaces";
    if (currentPage === 1) {
      const end = Math.min(ROOMS_ON_FIRST_PAGE, totalRooms);
      return `Showing 1–${end} of ${totalRooms} rooms`;
    }
    const start = ROOMS_ON_FIRST_PAGE + (currentPage - 2) * ROOMS_PER_PAGE + 1;
    const end = Math.min(ROOMS_ON_FIRST_PAGE + (currentPage - 1) * ROOMS_PER_PAGE, totalRooms);
    return `Showing ${start}–${end} of ${totalRooms} rooms`;
  }, [currentPage, totalRooms]);

  //: Open/close the create dialog, always clearing a previous failure.
  const setCreateOpen = (open: boolean) => {
    setCreateError("");
    setIsCreating(open);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setCreateError("");
    try {
      const newRoom = await createRoom({
        name: name.trim(),
        description: "",
        client_name: "",
        room_mode: isPrototypeMode() ? "manual_check" : roomMode,
      });
      setIsCreating(false);
      setName("");
      setRoomMode(isPrototypeMode() ? "manual_check" : "ai_comparison");
      openRoom(newRoom.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const isAuth = /\b40[13]\b|unauthor|forbidden/i.test(message);
      setCreateError(
        isAuth
          ? "Not authorised by the backend. The app could not read its API token — check that the backend service is running from a folder containing storage/secure/."
          : `Could not create the room: ${message}`
      );
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
        <div className="max-w-7xl mx-auto flex flex-col gap-6">
          <div className="flex items-center justify-between pb-4 border-b border-border-color">
            <Skeleton className="h-7 w-56 rounded-none" />
            <Skeleton className="h-9 w-36 rounded-none" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-44 w-full rounded-none" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex flex-col flex-1 w-full h-full bg-bg-dark overflow-y-auto select-none text-text-primary px-6 md:px-8 pt-10 md:pt-14 pb-6 md:pb-8"
    >
      <div className="max-w-7xl w-full mx-auto flex flex-col flex-1 min-h-full">

        {/* ── 1. Filters & View Controls Bar ── */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 p-2 bg-bg-card border border-border-color shrink-0 mb-4.5">
          {/* Left: Search Input */}
          <div className="relative flex-1 min-w-[240px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search..."
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

          {/* Center / Right: Filter Pills & Sort */}
          <div className="flex items-center gap-2.5 flex-wrap shrink-0">
            {/* Sort Selector */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 bg-bg-dark border border-border-color text-xs font-mono text-text-secondary">
              <ArrowUpDown size={12} className="text-text-muted" />
              <span className="text-[10px] text-text-muted uppercase hidden sm:inline">Sort:</span>
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

        {/* ── 2. Main CAD Content Area (Max 3 Rows) ── */}
        <div className="flex-1 flex flex-col justify-start">
          {filteredRooms.length === 0 ? (
            /* Empty Feedback */
            <div className="flex flex-col items-center justify-center p-12 bg-bg-card border border-border-color text-center my-auto">
              {rooms.length === 0 ? (
                <>
                  <Plus size={28} className="text-text-muted mb-3" />
                  <h3 className="text-sm font-mono font-bold uppercase tracking-wider text-text-primary mb-1">
                    NO WORKSPACES YET
                  </h3>
                  <p className="text-xs text-text-muted mb-4 font-sans max-w-sm">
                    Create a workspace to compare a reference drawing against its revision.
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCreateOpen(true)}
                    className="rounded-none font-mono text-xs uppercase"
                  >
                    Create Room
                  </Button>
                </>
              ) : (
                <>
                  <Search size={28} className="text-text-muted mb-3" />
                  <h3 className="text-sm font-mono font-bold uppercase tracking-wider text-text-primary mb-1">
                    NO MATCHING WORKSPACES FOUND
                  </h3>
                  <p className="text-xs text-text-muted mb-4 font-sans max-w-sm">
                    No CAD checking rooms match your current search query.
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setSearchQuery("")}
                    className="rounded-none font-mono text-xs uppercase"
                  >
                    Clear Search
                  </Button>
                </>
              )}
            </div>
          ) : (
            /* ── 4-COLUMN GRID BLUEPRINT GALLERY (MAX 3 ROWS) ── */
            <div
              className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-4 gap-4.5"
              data-tour="rooms-gallery"
            >
              {/* Quick Action "Start New Checking" Card - only on page 1 */}
              {currentPage === 1 && (
                <div
                  onClick={() => setCreateOpen(true)}
                  className="border-2 border-dashed border-border-color hover:border-accent-cyan bg-bg-card/40 hover:bg-accent-cyan/5 p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-all min-h-[220px] group rounded-none"
                >
                  <div className="w-12 h-12 border border-dashed border-border-color group-hover:border-accent-cyan group-hover:bg-accent-cyan/10 flex items-center justify-center text-text-muted group-hover:text-accent-cyan mb-3 transition-colors">
                    <Plus size={22} />
                  </div>
                  <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-text-primary group-hover:text-accent-cyan transition-colors">
                    Create New
                  </h3>
                  <p className="text-[11px] text-text-muted mt-1 max-w-[200px] font-sans">
                    Set up a new room for CAD drawing comparison.
                  </p>
                </div>
              )}

              {/* Checking Room Blueprint Cards */}
              {pageRooms.map((room) => {
                const hasPair = !!(room.active_old_drawing_name && room.active_new_drawing_name);
                return (
                  <div
                    key={room.id}
                    onClick={() => openRoom(room.id)}
                    title="Click to Open"
                    className="bg-bg-card border border-border-color hover:border-accent-cyan/70 p-4 flex flex-col gap-3 transition-all cursor-pointer group rounded-none shadow-sm hover:shadow-md hover:shadow-accent-cyan/5 relative"
                  >
                    {/* Card Header: Name, Status & Delete */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2.5 min-w-0">
                        <CadFileIcon size={20} className="text-text-muted group-hover:text-accent-cyan transition-colors shrink-0 mt-0.5" />
                        <div className="min-w-0">
                          <h3 className="text-base font-mono font-bold text-text-primary group-hover:text-accent-cyan transition-colors truncate tracking-tight">
                            {room.name}
                          </h3>
                          <div className="flex items-center gap-1.5 mt-0.5 min-w-0">
                            {hasPair ? (
                              <span
                                className="text-[11px] font-mono text-text-muted/70 truncate font-semibold group-hover:text-accent-cyan transition-colors"
                                title={room.active_new_drawing_name || undefined}
                              >
                                {room.active_new_drawing_name}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-mono text-text-muted/70">
                                <span>No drawing detected </span>
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Delete Action (X) */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingRoom({ id: room.id, name: room.name });
                        }}
                        className="p-1 text-text-muted hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer rounded-none shrink-0"
                        title="Delete Room"
                      >
                        <X size={14} />
                      </button>
                    </div>

                    {/* Real CAD Drawing Vector Thumbnail Viewport */}
                    <RealDrawingThumbnail
                      drawingId={room.active_new_drawing_id || room.active_old_drawing_id}
                      hasPair={hasPair}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── 3. Pagination Footer Bar (Max 3 Rows) ── */}
        {totalPages > 1 && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 pb-2 border-t border-border-color text-xs font-mono select-none shrink-0 mt-4.5">
            {/* Item Range Info */}
            <div className="text-text-muted text-[11px]">
              {itemRangeText}
              <span className="text-text-muted/60 ml-1.5 hidden sm:inline">
                (Page {currentPage} of {totalPages})
              </span>
            </div>

            {/* Navigation Controls */}
            <div className="flex items-center gap-1">
              {/* Previous Page */}
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage <= 1}
                onClick={() => handlePageChange(currentPage - 1)}
                className="h-7 px-2 gap-1 rounded-none text-xs font-mono cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                title="Previous"
              >
                <ChevronLeft size={13} />
              </Button>

              {/* Page Numbers */}
              <div className="flex items-center gap-1 mx-1">
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter((p) => {
                    return (
                      p === 1 ||
                      p === totalPages ||
                      Math.abs(p - currentPage) <= 1
                    );
                  })
                  .map((page, idx, arr) => {
                    const prev = arr[idx - 1];
                    const hasGap = prev && page - prev > 1;
                    return (
                      <React.Fragment key={page}>
                        {hasGap && (
                          <span className="px-1 text-text-muted/50 select-none">…</span>
                        )}
                        <button
                          onClick={() => handlePageChange(page)}
                          className={`h-7 min-w-[28px] px-2 text-xs font-mono font-semibold transition-colors cursor-pointer border ${currentPage === page
                            ? "bg-accent-cyan text-on-accent border-accent-cyan"
                            : "bg-bg-dark text-text-secondary border-border-color hover:bg-sidebar-item-hover hover:text-text-primary"
                            }`}
                        >
                          {page}
                        </button>
                      </React.Fragment>
                    );
                  })}
              </div>

              {/* Next Page */}
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage >= totalPages}
                onClick={() => handlePageChange(currentPage + 1)}
                className="h-7 px-2 gap-1 rounded-none text-xs font-mono cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                title="Next"
              >
                <ChevronRight size={13} />
              </Button>
            </div>
          </div>
        )}

      </div>

      {/* ── 4. Create Checking Room Dialog (Global Modal Standard) ── */}
      <Modal
        isOpen={isCreating}
        onClose={() => setCreateOpen(false)}
        title="Create Checking Room"
        description="Set up a new room to compare drawings."
        maxWidthClassName="max-w-lg"
        footer={
          <div className="flex items-center justify-end gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCreateOpen(false)}
              className="rounded-none font-mono font-bold text-xs uppercase px-4 h-9 cursor-pointer"
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              form="create-room-form"
              disabled={!name.trim()}
              className="rounded-none font-mono font-bold text-xs uppercase px-5 h-9 gap-1.5 cursor-pointer"
            >
              <span>Create</span>
              <ArrowRight size={13} />
            </Button>
          </div>
        }
      >
        <form id="create-room-form" onSubmit={handleCreate} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-mono font-bold uppercase tracking-wider text-text-secondary">
                Room Name
              </label>
              <span className="text-[12px] font-mono text-red-500 uppercase font-semibold">
                *
              </span>
            </div>
            <input
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter a name to identify this drawing."
              required
              className="w-full bg-bg-dark border border-border-color focus:border-accent-cyan px-3.5 py-2.5 text-sm text-text-primary outline-none transition-colors rounded-none font-mono placeholder:text-text-muted/50"
            />
            {createError && (
              <div
                role="alert"
                className="mt-1 px-3 py-2 border border-rose-500/40 bg-rose-500/10 text-[11px] leading-relaxed text-rose-300"
              >
                {createError}
              </div>
            )}
          </div>
        </form>
      </Modal>

      {/* ── 5. Global Deletion Confirm Modal ── */}
      <ConfirmModal
        isOpen={!!deletingRoom}
        onClose={() => !isDeleting && setDeletingRoom(null)}
        onConfirm={handleConfirmDelete}
        title="Delete Room"
        message={
          <div className="flex flex-col gap-1.5">
            <p>
              Are you sure you want to delete room <strong className="font-mono text-text-primary">"{deletingRoom?.name}"</strong>?
            </p>
            <p className="text-[11px] text-text-muted leading-relaxed">
              All linked CAD drawing vectors, ground truth markings, and session history will be permanently removed.
            </p>
          </div>
        }
        confirmText="Delete Room"
        cancelText="Cancel"
        variant="danger"
        isLoading={isDeleting}
      />
    </div>
  );
};
