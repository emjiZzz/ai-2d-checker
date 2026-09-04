import React, { useState, useEffect, useCallback } from "react";
import { LayoutTemplate, Save, Trash2, Check, Move, RefreshCw, X, Star } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useReviewStore } from "../../stores/reviewStore";
import { recordHistoryGroup, type HistoryEntry } from "../../stores/historyStore";
import { zonesToTemplatePayload } from "../../utils/zoneFractions";
import { Button } from "../ui/Button";
import {
  fetchAllZoneTemplates,
  saveZoneTemplate,
  deleteZoneTemplate,
  setDefaultZoneTemplate,
  zoneSignature,
  ZONE_KEYS,
  type ZoneTemplate,
} from "../../services/drawingsApi";

interface SavedTemplatesModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SavedTemplatesModal: React.FC<SavedTemplatesModalProps> = ({ isOpen, onClose }) => {
  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const newDrawing = useWorkspaceStore((s) => s.newDrawing);
  const zoneState = useWorkspaceStore((s) => s.zoneRegions);
  const isRoiEditModeEnabled = useReviewStore((s) => s.isRoiEditModeEnabled);
  const setRoiEditMode = useReviewStore((s) => s.setRoiEditMode);
  const setSelectedComparisonRegion = useReviewStore((s) => s.setSelectedComparisonRegion);
  const applyZoneTemplate = useReviewStore((s) => s.applyZoneTemplate);

  const [templates, setTemplates] = useState<ZoneTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const activeDrawing = oldDrawing ?? newDrawing;
  const signature = activeDrawing ? zoneSignature(activeDrawing.metadata?.render_bounds) : null;

  const loadTemplates = useCallback(async () => {
    setIsLoading(true);
    try {
      const list = await fetchAllZoneTemplates();
      setTemplates(list);
    } catch (err) {
      console.warn("Failed to load zone templates:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadTemplates();
    }
  }, [isOpen, loadTemplates]);

  if (!isOpen) return null;

  /**
   * Stamps a template over BOTH panes, as one undoable action.
   *
   * This rewrites every zone on both drawings from the template's set, which can move zones the
   * user never touched on this sheet — the same destructive reach as Reset, and until now with
   * no way back at all, because this modal recorded no history whatsoever. The toolbar's
   * `saveZonesAsTemplate` was undoable and this was not, for the identical operation.
   *
   * Grouped: the user clicked once, so one Ctrl+Z takes both panes back. Recording per drawing
   * inside the loop is what made undo restore one pane and leave the other — see
   * `docs/vault/06 - .../Gotcha - One Click on Two Panes Recorded Two Undo Steps.md`.
   *
   * Only the LOCAL boxes are walked back. The template stays saved on the server, since that is
   * a deliberate cross-drawing decision and not something a keystroke should silently retract.
   */
  const applyToBothPanes = (zones: Record<string, any>) => {
    const entries: HistoryEntry[] = [];
    for (const d of [oldDrawing, newDrawing]) {
      if (!d) continue;
      const detected = zoneState[d.id];
      const bounds = d.metadata?.render_bounds;
      const before = useReviewStore.getState().customRegions[d.id] ?? null;
      const pinnedBefore = useReviewStore.getState().pinnedZoneKeys[d.id] ?? null;
      applyZoneTemplate(
        d.id,
        zones as any,
        detected as any,
        bounds as [number, number, number, number]
      );
      entries.push({
        kind: "zone/bulk",
        label: "Apply sheet template",
        drawingId: d.id,
        before,
        after: useReviewStore.getState().customRegions[d.id] ?? null,
        pinnedBefore,
        pinnedAfter: useReviewStore.getState().pinnedZoneKeys[d.id] ?? null,
      });
    }
    recordHistoryGroup(entries);
  };

  const handleSaveTemplate = async () => {
    if (!signature || !activeDrawing) {
      setStatusMsg({ type: "error", text: "No active drawing signature available" });
      return;
    }
    const oldReg = oldDrawing ? useReviewStore.getState().getRegionsFor(oldDrawing.id) : {};
    const newReg = newDrawing ? useReviewStore.getState().getRegionsFor(newDrawing.id) : {};
    const regions = { ...oldReg, ...newReg };

    // Only persist real comparison zones. `regions` can carry non-zone keys
    // (e.g. drawing_id, render_bounds) copied from the zones response object;
    // saving those pollutes the template. Backend strips them too — belt and braces.
    const allowed = new Set<string>(ZONE_KEYS);
    const zoneOnly = Object.fromEntries(
      Object.entries(regions).filter(([key, frac]) => frac && allowed.has(key)),
    );
    // Shaped by the shared, tested helper rather than an inline four-field literal. The literal
    // that used to be here enumerated xMin/xMax/yMin/yMax and therefore dropped `points`,
    // flattening every hand-drawn outline to its bounding box — and `applyZoneTemplate` below
    // then wrote the flattened version straight back over the live regions, so a reshape
    // vanished on screen at the moment of saving it. That defect was fixed in the toolbar's
    // `saveZonesAsTemplate` and left standing here.
    // See `docs/vault/06 - .../Gotcha - A Reshaped Zone Was Flattened by the Template Round Trip.md`.
    const zones = zonesToTemplatePayload(zoneOnly) as Record<string, any>;

    try {
      await saveZoneTemplate(signature, { name: templateName || signature, zones });

      // Immediately apply saved template to both drawings in workspace store
      applyToBothPanes(zones);

      setStatusMsg({ type: "success", text: `Saved template with ${Object.keys(zones).length} pinned zone(s)` });
      setTemplateName("");
      loadTemplates();
    } catch (err) {
      setStatusMsg({ type: "error", text: err instanceof Error ? err.message : String(err) });
    }
  };

  const handleApplyTemplate = (tpl: ZoneTemplate) => {
    applyToBothPanes(tpl.zones as Record<string, any>);
    setStatusMsg({ type: "success", text: `Applied template ${tpl.name || tpl.signature}` });
  };

  const handleDeleteTemplate = async (sig: string) => {
    if (window.confirm(`Delete zone template '${sig}'?`)) {
      try {
        await deleteZoneTemplate(sig);
        setStatusMsg({ type: "success", text: `Deleted template ${sig}` });
        loadTemplates();
      } catch (err) {
        setStatusMsg({ type: "error", text: err instanceof Error ? err.message : String(err) });
      }
    }
  };

  const handleSetDefault = async (tpl: ZoneTemplate) => {
    // Toggle: clicking the current default clears it; clicking another makes it the sole default.
    const next = !tpl.is_default;
    try {
      await setDefaultZoneTemplate(tpl.signature, next);
      setStatusMsg({
        type: "success",
        text: next
          ? `${tpl.name || tpl.signature} is now the default template`
          : `Cleared default template`,
      });
      loadTemplates();
    } catch (err) {
      setStatusMsg({ type: "error", text: err instanceof Error ? err.message : String(err) });
    }
  };

  const toggleZoneEditMode = () => {
    const nextState = !isRoiEditModeEnabled;
    setRoiEditMode(nextState);
    if (nextState && !useReviewStore.getState().selectedComparisonRegion) {
      setSelectedComparisonRegion("title");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-fade-in">
      <div className="bg-bg-card border border-border-color rounded-2xl shadow-2xl w-full max-w-md p-6 flex flex-col gap-4 relative animate-scale-in">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-text-muted hover:text-text-primary p-1 rounded-lg hover:bg-sidebar-item-hover transition-colors cursor-pointer"
        >
          <X size={18} />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-2.5 border-b border-border-color pb-3">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400">
            <LayoutTemplate size={20} />
          </div>
          <div>
            <h3 className="text-base font-bold text-text-primary leading-tight">Saved Sheet Templates</h3>
            <p className="text-xs text-text-muted">Manage aspect-ratio zone layout templates</p>
          </div>
        </div>

        {/* Active Sheet Badge & Alignment Toggle */}
        <div className="flex items-center justify-between p-3 bg-bg-dark rounded-xl border border-border-color/70 text-xs">
          <div className="flex flex-col gap-0.5">
            <span className="text-text-muted font-medium">Active Sheet Aspect</span>
            <span className="text-amber-400 font-mono font-bold">{signature || "No active drawing"}</span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={toggleZoneEditMode}
            className={`h-8 text-xs gap-1.5 border transition-colors ${
              isRoiEditModeEnabled
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                : "text-text-muted hover:text-text-primary border-border-color"
            }`}
          >
            <Move size={13} />
            <span>{isRoiEditModeEnabled ? "Editing Zones" : "Edit Zones"}</span>
          </Button>
        </div>

        {/* Status Alert */}
        {statusMsg && (
          <div
            className={`p-2.5 rounded-lg text-xs font-semibold ${
              statusMsg.type === "error"
                ? "bg-red-500/10 text-red-400 border border-red-500/20"
                : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
            }`}
          >
            {statusMsg.text}
          </div>
        )}

        {/* Save Current Alignment Form */}
        <div className="flex flex-col gap-2 p-3 bg-bg-dark/50 rounded-xl border border-border-color/50">
          <label className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            Save Current Sheet Alignment
          </label>
          <input
            type="text"
            placeholder="Template name e.g. A3 Standard"
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            className="w-full bg-bg-dark border border-border-color rounded-lg py-2 px-3 text-xs text-text-primary focus:outline-none focus:border-amber-400"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={handleSaveTemplate}
            disabled={!signature}
            className="w-full h-9 text-xs bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20 gap-1.5 justify-center"
          >
            <Save size={14} />
            <span>Save Current Alignment to Template</span>
          </Button>
        </div>

        {/* List Header & Refresh */}
        <div className="flex flex-col gap-1 mt-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-text-muted uppercase tracking-wider">
              Stored Templates ({templates.length})
            </span>
            <button
              onClick={loadTemplates}
              title="Refresh templates list"
              className="text-text-muted hover:text-text-primary transition-colors cursor-pointer p-1"
            >
              <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
            </button>
          </div>
          <p className="text-[10px] text-text-muted leading-snug">
            <Star size={9} className="inline fill-sky-400 text-sky-400 -mt-0.5" /> The default
            template is applied to any sheet without its own matching aspect template.
          </p>
        </div>

        {/* Templates List */}
        <div className="max-h-56 overflow-y-auto flex flex-col gap-2 pr-1">
          {templates.length === 0 ? (
            <div className="text-xs text-text-muted italic py-6 text-center bg-bg-dark/40 rounded-xl border border-border-color/30">
              No saved sheet templates found.
            </div>
          ) : (
            templates.map((tpl) => {
              const isMatch = tpl.signature === signature;
              const isDefault = tpl.is_default;
              const pinnedCount = Object.keys(tpl.zones || {}).length;
              return (
                <div
                  key={tpl.signature}
                  className={`p-3 rounded-xl border text-xs flex items-center justify-between transition-all ${
                    isMatch
                      ? "bg-amber-500/10 border-amber-500/40 text-text-primary shadow-xs"
                      : "bg-bg-dark border-border-color/60 text-text-muted hover:border-border-color"
                  }`}
                >
                  <div className="flex flex-col gap-1 min-w-0 pr-2">
                    <div className="flex items-center gap-2">
                      <span className="font-bold font-mono text-text-primary truncate">
                        {tpl.name || tpl.signature}
                      </span>
                      {isDefault && (
                        <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30 flex items-center gap-1">
                          <Star size={9} className="fill-current" /> Default
                        </span>
                      )}
                      {isMatch && (
                        <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                          Matches Current Sheet
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] font-mono text-text-muted">
                      {tpl.signature} · {pinnedCount} Pinned Zone{pinnedCount === 1 ? "" : "s"}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      onClick={() => handleSetDefault(tpl)}
                      className={`p-1.5 rounded-lg border transition-colors cursor-pointer ${
                        isDefault
                          ? "bg-sky-500/20 text-sky-300 border-sky-500/40"
                          : "bg-transparent text-text-muted border-border-color hover:text-sky-300 hover:border-sky-500/40"
                      }`}
                      title={isDefault ? "Clear as default template" : "Set as default template for all sheets"}
                    >
                      <Star size={13} className={isDefault ? "fill-current" : ""} />
                    </button>
                    <button
                      onClick={() => handleApplyTemplate(tpl)}
                      className="p-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 transition-colors cursor-pointer flex items-center gap-1 text-[11px] font-bold"
                      title="Apply this template's pinned zones to current drawings"
                    >
                      <Check size={13} />
                      <span>Apply</span>
                    </button>
                    <button
                      onClick={() => handleDeleteTemplate(tpl.signature)}
                      className="p-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 transition-colors cursor-pointer"
                      title="Delete saved template"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
