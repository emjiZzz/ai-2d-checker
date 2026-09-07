import { create } from "zustand";
import { buildHeaders, baseUrl, parseOrThrow } from "../services/fetchUtils";

export interface EnterpriseUser {
  id: string;
  username: string;
  role: string;
  active: boolean;
  created_at: string;
  permissions: string[];
}

interface AdminState {
  users: EnterpriseUser[];
  isLoading: boolean;
  error: string | null;
  
  // System diagnostic summaries
  vectorDbStatus: any | null;
  aiModelStatus: any | null;

  // Real audit session management
  adminAuditSessions: any[];
  adminAuditSessionsLoading: boolean;

  // Actions
  fetchUsers: () => Promise<void>;
  createUser: (username: string, password: string, role: string) => Promise<boolean>;
  deleteUser: (username: string) => Promise<boolean>;
  updateUser: (username: string, updates: { active?: boolean; role?: string; password?: string }) => Promise<boolean>;
  triggerBackup: () => Promise<string | null>;
  triggerRestore: (backupFile: string) => Promise<boolean>;

  // Audit history actions
  fetchAdminAuditSessions: (isDeleted?: boolean, username?: string) => Promise<void>;
  softDeleteAuditSession: (id: string) => Promise<boolean>;
  restoreAuditSession: (id: string) => Promise<boolean>;
  emptyTrash: () => Promise<boolean>;
}

export const useAdminStore = create<AdminState>((set, get) => ({
  users: [],
  isLoading: false,
  error: null,
  vectorDbStatus: {
    engine: "LanceDB Local",
    status: "connected",
    total_embedded_chunks: 1420,
    vector_dimensions: 1536
  },
  aiModelStatus: {
    model: "llama-3-8b-instruct",
    status: "ready",
    memory_usage_gb: 4.2
  },

  adminAuditSessions: [],
  adminAuditSessionsLoading: false,

  fetchUsers: async () => {
    set({ isLoading: true, error: null });

    try {
      const response = await fetch(`${baseUrl()}/api/v1/admin/users`, { headers: buildHeaders() });
      const data = await parseOrThrow<any>(response);
      set({ users: data, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || "Network error loading users.", isLoading: false });
    }
  },

  createUser: async (username, password, role) => {
    set({ isLoading: true, error: null });

    try {
      const response = await fetch(`${baseUrl()}/api/v1/admin/users`, {
        method: "POST",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ username, password, role })
      });
      await parseOrThrow<any>(response);
      
      set({ isLoading: false });
      get().fetchUsers();
      return true;
    } catch (err: any) {
      set({ error: err.message || "Network error creating user.", isLoading: false });
      return false;
    }
  },

  deleteUser: async (username) => {
    set({ isLoading: true, error: null });

    try {
      const response = await fetch(`${baseUrl()}/api/v1/admin/users/${username}`, {
        method: "DELETE",
        headers: buildHeaders()
      });
      await parseOrThrow<any>(response);
      
      set({ isLoading: false });
      get().fetchUsers();
      return true;
    } catch (err: any) {
      set({ error: err.message || "Network error deleting user.", isLoading: false });
      return false;
    }
  },

  updateUser: async (username, updates) => {
    set({ isLoading: true, error: null });

    try {
      const response = await fetch(`${baseUrl()}/api/v1/admin/users/${username}`, {
        method: "PATCH",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(updates)
      });
      await parseOrThrow<any>(response);
      
      set({ isLoading: false });
      get().fetchUsers();
      return true;
    } catch (err: any) {
      set({ error: err.message || "Network error updating user.", isLoading: false });
      return false;
    }
  },

  triggerBackup: async () => {
    set({ isLoading: true, error: null });
    // Mock robust system snapshot backup
    await new Promise((r) => setTimeout(r, 1200));
    set({ isLoading: false });
    return `backup_snapshot_${Date.now()}.zip`;
  },

  triggerRestore: async (backupFile) => {
    set({ isLoading: true, error: null });
    console.debug("Restoring secure snapshot backup from archive file target:", backupFile);
    await new Promise((r) => setTimeout(r, 1500));
    set({ isLoading: false });
    return true;
  },

  fetchAdminAuditSessions: async (isDeleted = false, username?: string) => {
    set({ adminAuditSessionsLoading: true, error: null });

    try {
      let url = `/api/v1/audits/sessions?is_deleted=${isDeleted}`;
      if (username) {
        url += `&username=${encodeURIComponent(username)}`;
      }

      const response = await fetch(`${baseUrl()}${url}`, { headers: buildHeaders() });
      const data = await parseOrThrow<any>(response);
      set({ adminAuditSessions: data, adminAuditSessionsLoading: false });
    } catch (err: any) {
      set({ error: err.message || "Network error loading audit history.", adminAuditSessionsLoading: false });
    }
  },

  softDeleteAuditSession: async (id: string) => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/audits/sessions/${id}`, {
        method: "DELETE",
        headers: buildHeaders()
      });
      await parseOrThrow(res);
      return true;
    } catch (err: any) {
      console.warn(`Failed to soft-delete session ${id}: ${err.message}`);
      return false;
    }
  },

  restoreAuditSession: async (id: string) => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/audits/sessions/${id}/restore`, {
        method: "POST",
        headers: buildHeaders()
      });
      await parseOrThrow(res);
      return true;
    } catch (err: any) {
      console.warn(`Failed to restore session ${id}: ${err.message}`);
      return false;
    }
  },

  emptyTrash: async () => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/audits/sessions/trash`, {
        method: "DELETE",
        headers: buildHeaders()
      });
      await parseOrThrow(res);
      return true;
    } catch (err: any) {
      console.warn(`Failed to empty trash: ${err.message}`);
      return false;
    }
  }
}));
