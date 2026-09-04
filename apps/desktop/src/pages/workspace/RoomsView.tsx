import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  Plus,
  X,
  ArrowRight,
  Search,
  ArrowUpDown,
  HelpCircle
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

const ITEMS_PER_PAGE = 24;

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
   *
   * Waits for the engineer-identity prompt. This effect used to fire on mount, and in a
   * prototype build `RoomsView` mounts underneath `EngineerPromptModal` — so a first launch
   * opened the tour on top of the name prompt, before the tester had entered anything. It was
   * not even a z-index accident to be nudged: the prompt's backdrop is `z-[100000]` and
   * deliberately opaque, the tour is `z-[999999]`, so the tour wins by design and always will.
   * The trigger was the thing that was wrong.
   *
   * Once the tester proceeds, `setEngineerName` clears `isModalOpen`, this re-runs, and the tour
   * starts then — which is the intended sequence and what it now does.
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

  // Search & Sort State
  const [searchQuery, setSearchQuery] = useState("");
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

  // Reset pagination limit on filter/search change
  useEffect(() => {
    setDisplayLimit(ITEMS_PER_PAGE);
  }, [searchQuery, sortBy]);

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

  //: Open/close the create dialog, always clearing a previous failure. A stale "not
  //: authorised" sitting over a fresh attempt is its own small lie.
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
      /*
        This was `catch { // rollback handled by useRooms }` -- an empty block.

        Rollback IS handled there, but rollback is not feedback: `useCreateRoom.onError` only
        restores the pre-mutation list, so a failed create showed the optimistic row appear, blink
        out, and nothing else. The dialog stayed open with the name still in it. Reported from the
        installed prototype as "I can't create a room and proceed", and the button genuinely looked
        dead.

        Every cause looked identical, which is what made it expensive. The real one was a 401:
        an installed build cannot find `storage/secure/.api-token`, so it holds no bearer token --
        while `/health` needs none and returns 200, so the app reports itself connected. A network
        failure, a duplicate name and an auth failure were all rendered as "nothing happened".

        401 and 403 are called out by name because they are the ones a user cannot act on from
        this dialog, and the remedy is somewhere else entirely.
      */
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
    <div className="flex flex-col flex-1 w-full h-full bg-bg-dark overflow-y-auto select-none text-text-primary p-6 md:p-8">
      <div className="max-w-7xl w-full mx-auto flex flex-col flex-1 gap-6">

        {/* ── 1. CAD Hub Header ── */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-border-color">
          <div>
            <h1 className="text-xl md:text-2xl font-black font-mono tracking-wider uppercase text-text-primary">
              Inspection Workspaces
            </h1>
            <p className="text-xs text-text-muted mt-0.5">
              Manage drawing comparison sessions, check reference vs revision CAD files, and label errors.
            </p>
          </div>
        </div>

        {/* ── 2. Filters & View Controls Bar ── */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 p-2 bg-bg-card border border-border-color">
          {/* Left: Search Input */}
          <div className="relative flex-1 min-w-[240px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter drawings or room names... (Press '/' to focus)"
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

          {/* Center / Right: Filter Pills, Sort & Quick Tour */}
          <div className="flex items-center gap-2.5 flex-wrap shrink-0">
            {/* Quick Tour Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => startTour()}
              className="rounded-none font-mono text-xs uppercase px-2.5 py-1 h-[26px] flex items-center gap-1.5 text-text-muted hover:text-accent-cyan border-border-color cursor-pointer bg-bg-dark"
              title="Explore Quick Tour & Onboarding Guide"
            >
              <HelpCircle size={13} className="text-accent-cyan" />
              <span>Quick Tour</span>
            </Button>

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

        {/* ── 3. Main CAD Content Area ── */}
        {filteredRooms.length === 0 ? (
          /* Empty Feedback — and the two empty states are NOT the same state.
           *
           * "Nothing matches your search" and "you have no workspaces yet" were one branch, which
           * told a fresh install that no rooms matched a search query it had not typed and offered
           * it a Clear Search button for an empty search. The only route to `setIsCreating(true)`
           * is the "Create New" card in the grid below, and the grid does not render when there
           * are no rooms — so a new install had no way to create its first workspace at all.
           */
          <div className="flex flex-col items-center justify-center p-12 bg-bg-card border border-border-color text-center my-6">
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
                  No CAD inspection rooms match your current search query.
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
          /* ── 4-COLUMN GRID BLUEPRINT GALLERY ── */
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-4 gap-4.5" data-tour="rooms-gallery">
            {/* Quick Action "Start New Inspection" Card */}
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
                Set up a new workspace for CAD drawing comparison.
              </p>
            </div>

            {/* Inspection Room Blueprint Cards */}
            {visibleRooms.map((room) => {
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
                      <CadFileIcon size={18} className="text-text-muted group-hover:text-accent-cyan transition-colors shrink-0 mt-0.5" />
                      <div className="min-w-0">
                        <h3 className="text-sm font-mono font-bold text-text-primary group-hover:text-accent-cyan transition-colors truncate">
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

        {/* Lazy Loading Sentinel */}
        {displayLimit < filteredRooms.length && (
          <div ref={sentinelRef} className="py-6 flex items-center justify-center text-xs font-mono text-text-muted">
            <div className="w-4 h-4 border-2 border-accent-cyan border-t-transparent animate-spin mr-2" />
            <span>Loading additional rooms...</span>
          </div>
        )}

      </div>

      {/* ── 4. Create Inspection Room Dialog (Global Modal Standard) ── */}
      <Modal
        isOpen={isCreating}
        onClose={() => setCreateOpen(false)}
        title="Create Inspection Room"
        description="Set up a new workspace to compare drawing revisions."
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
              <span className="text-[10px] font-mono text-accent-cyan uppercase font-semibold">
                Required
              </span>
            </div>
            <input
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. M7452 Bracket Rev B"
              required
              className="w-full bg-bg-dark border border-border-color focus:border-accent-cyan px-3.5 py-2.5 text-sm text-text-primary outline-none transition-colors rounded-none font-mono placeholder:text-text-muted/50"
            />
            <p className="text-xs text-text-muted">
              Enter a name to identify this drawing inspection.
            </p>
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
        title="DELETE INSPECTION ROOM"
        message={
          <div className="flex flex-col gap-1.5">
            <p>
              Are you sure you want to permanently delete room <strong className="font-mono text-text-primary">"{deletingRoom?.name}"</strong>?
            </p>
            <p className="text-[11px] text-text-muted">
              All linked CAD drawing vectors, ground truth markings, and session history will be removed.
            </p>
          </div>
        }
        confirmText="DELETE ROOM"
        cancelText="CANCEL"
        variant="danger"
        isLoading={isDeleting}
      />
    </div>
  );
};
