import { create } from "zustand";
import { AuditState } from "./audit/types";
import { createStandardsSlice } from "./audit/slices/createStandardsSlice";
import { createSessionsSlice } from "./audit/slices/createSessionsSlice";

export type {
  StandardDocument,
  AuditSession,
  AuditViolation,
} from "./audit/types";

export const useAuditStore = create<AuditState>((set, get, store) => ({
  ...createStandardsSlice(set, get, store),
  ...createSessionsSlice(set, get, store),
}));
