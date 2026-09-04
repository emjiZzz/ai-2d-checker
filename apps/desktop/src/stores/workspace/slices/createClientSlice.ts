import { StateCreator } from "zustand";
import { WorkspaceState, ClientSlice } from "../types";

export const createClientSlice: StateCreator<WorkspaceState, [], [], ClientSlice> = (set) => ({
  selectedClient: null,
  setSelectedClient: (name) => set({ selectedClient: name }),
});
