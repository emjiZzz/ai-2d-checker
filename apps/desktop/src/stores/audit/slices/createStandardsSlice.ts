import { StateCreator } from "zustand";
import { AuditState, StandardsSlice } from "../types";
import { logger } from "../../../services/logger";
import { buildHeaders, baseUrl, uploadFile, parseOrThrow } from "../../../services/fetchUtils";
import { queryClient } from "../../../services/queryClient";
import { standardKeys } from "../../../services/queryKeys";

export const createStandardsSlice: StateCreator<AuditState, [], [], StandardsSlice> = (set) => ({
  standards: [],
  activeStandard: null,
  uploadStatus: "idle",
  uploadProgress: 0,

  fetchStandards: async () => {
    try {
      const response = await fetch(`${baseUrl()}/api/v1/standards`, { headers: buildHeaders() });
      const data = await parseOrThrow<any>(response);
      set({ standards: data });
    } catch (err: any) {
      logger.warn(`Failed to fetch engineering standards list: ${err.message}`);
    }
  },

  uploadStandard: async (file: File, name: string, category = "", description = "", scope = "universal", clientName = "") => {
    set({
      uploadStatus: "uploading",
      uploadProgress: 10,
      errorMessage: null,
    });

    logger.info(`Uploading engineering standard: ${name} (${file.name}) [Scope: ${scope}]`);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", name);
    if (category) formData.append("category", category);
    if (description) formData.append("description", description);
    formData.append("scope", scope);
    if (clientName && scope === "client_specific") formData.append("client_name", clientName);

    try {
      await uploadFile<any>(
        "/api/v1/standards",
        formData,
        (percent) => set({ uploadProgress: percent })
      );

      set({
        uploadStatus: "success",
        uploadProgress: 100,
        // Since uploadResult is the raw standard document now, we can set it
        // active directly without needing to fetch from an array. We'll leave
        // activeStandard unchanged since the return type isn't fully typed right now
        // but we WILL invalidate the TanStack Query cache so the UI updates.
      });

      queryClient.invalidateQueries({ queryKey: standardKeys.lists() });
      
      return true;
    } catch (err: any) {
      set({ uploadStatus: "error", errorMessage: err.message, uploadProgress: 0 });
      return false;
    }
  },

  deleteStandard: async (id: string) => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/standards/${id}`, {
        method: "DELETE",
        headers: buildHeaders()
      });
      await parseOrThrow(res);
      set((state) => ({
        standards: state.standards.filter((s) => s.id !== id),
        activeStandard: state.activeStandard?.id === id ? null : state.activeStandard,
      }));
      return true;
    } catch (err: any) {
      logger.warn(`Failed to delete standard ${id}: ${err.message}`);
      return false;
    }
  },

  updateStandard: async (id: string, updates: Partial<{ name: string; description: string; category: string }>) => {
    try {
      const params = new URLSearchParams();
      if (updates.name) params.append("name", updates.name);
      if (updates.description) params.append("description", updates.description);
      if (updates.category) params.append("category", updates.category);

      const res = await fetch(`${baseUrl()}/api/v1/standards/${id}?${params.toString()}`, {
        method: "PATCH",
        headers: buildHeaders()
      });
      const data = await parseOrThrow<any>(res);
      
      set((state) => ({
        standards: state.standards.map((s) => s.id === id ? data : s),
        activeStandard: state.activeStandard?.id === id ? data : state.activeStandard,
      }));
      return true;
    } catch (err: any) {
      logger.warn(`Failed to update standard ${id}: ${err.message}`);
      return false;
    }
  },
});
