import React from "react";
import { X, Edit2, Lock, Sparkles, Eye, EyeOff, AlertTriangle, UserX } from "lucide-react";
import { Button } from "../../../components/ui/Button";
import { EnterpriseUser } from "../../../stores/adminStore";

export interface UserModalsProps {
  editingUser: EnterpriseUser | null;
  setEditingUser: (user: EnterpriseUser | null) => void;
  editRole: string;
  setEditRole: (role: string) => void;
  handleEditSave: () => void;
  
  resettingUser: string | null;
  setResettingUser: (username: string | null) => void;
  resetPasswordText: string;
  setResetPasswordText: (text: string) => void;
  showResetPassword: boolean;
  setShowResetPassword: (show: boolean) => void;
  handleGenerateResetPassword: () => void;
  handleResetPasswordSave: () => void;
  
  deletingUser: string | null;
  setDeletingUser: (username: string | null) => void;
  handleDeleteConfirm: () => void;
  
  isLoading: boolean;
}

export const UserModals: React.FC<UserModalsProps> = ({
  editingUser,
  setEditingUser,
  editRole,
  setEditRole,
  handleEditSave,
  
  resettingUser,
  setResettingUser,
  resetPasswordText,
  setResetPasswordText,
  showResetPassword,
  setShowResetPassword,
  handleGenerateResetPassword,
  handleResetPasswordSave,
  
  deletingUser,
  setDeletingUser,
  handleDeleteConfirm,
  
  isLoading
}) => {
  return (
    <>
      {/* Frosted Glass Overlay for Editing User Details */}
      {editingUser && (
        <div className="frosted-glass-overlay">
          <div className="overlay-card card settings-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h4 className="card-title" style={{ margin: 0, borderLeft: "3px solid var(--accent-cyan)", paddingLeft: "8px", fontSize: "0.9rem" }}>
                <Edit2 size={16} style={{ color: "var(--accent-cyan)", marginRight: "6px" }} />
                Edit Enterprise Account
              </h4>
              <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" onClick={() => setEditingUser(null)}>
                <X size={16} />
              </Button>
            </div>
            <p className="overlay-desc" style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "8px" }}>
              Modifying attributes for account identity: <strong style={{ color: "var(--text-primary)" }}>{editingUser.username}</strong>
            </p>

            <div className="form-group" style={{ marginTop: "16px" }}>
              <label className="form-label">Username / Login ID</label>
              <input
                type="text"
                className="form-input"
                value={editingUser.username}
                disabled
                style={{ opacity: 0.6, cursor: "not-allowed" }}
              />
            </div>

            <div className="form-group" style={{ marginTop: "12px" }}>
              <label className="form-label">Role Classification</label>
              <select
                className="form-input select-input"
                value={editRole}
                onChange={(e) => setEditRole(e.target.value)}
                disabled={editingUser.username === "admin" || isLoading}
              >
                <option value="user">User (Auditing Engineer)</option>
                <option value="admin">Admin (System Administrator)</option>
              </select>
              {editingUser.username === "admin" && (
                <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "4px" }}>
                  🔒 Default System Admin role is locked to prevent administrative lockout.
                </p>
              )}
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "24px" }}>
              <Button
                variant="secondary"
                onClick={() => setEditingUser(null)}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleEditSave}
                disabled={isLoading}
                className="flex-1"
              >
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Frosted Glass Overlay for Password Resets */}
      {resettingUser && (
        <div className="frosted-glass-overlay">
          <div className="overlay-card card settings-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h4 className="card-title" style={{ margin: 0, borderLeft: "3px solid var(--accent-cyan)", paddingLeft: "8px", fontSize: "0.9rem" }}>
                <Lock size={16} style={{ color: "var(--accent-cyan)", marginRight: "6px" }} />
                Reset Account Credentials
              </h4>
              <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" onClick={() => setResettingUser(null)}>
                <X size={16} />
              </Button>
            </div>
            <p className="overlay-desc" style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "8px" }}>
              Generating or entering a new password for account identity: <strong style={{ color: "var(--text-primary)" }}>{resettingUser}</strong>
            </p>

            <div className="form-group" style={{ marginTop: "16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <label className="form-label" style={{ margin: 0 }}>New Account Password</label>
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="text-xs text-blue-500 hover:text-blue-600 p-0 h-auto gap-1"
                  onClick={handleGenerateResetPassword}
                >
                  <Sparkles size={12} />
                  Random Secure
                </Button>
              </div>
              <div className="input-icon-wrapper" style={{ position: "relative", display: "flex", alignItems: "center" }}>
                <input
                  type={showResetPassword ? "text" : "password"}
                  className="form-input"
                  style={{ paddingRight: "40px" }}
                  placeholder="Enter new strong password"
                  value={resetPasswordText}
                  onChange={(e) => setResetPasswordText(e.target.value)}
                  required
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
                  onClick={() => setShowResetPassword(!showResetPassword)}
                >
                  {showResetPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </Button>
              </div>
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "20px" }}>
              <Button
                variant="secondary"
                onClick={() => setResettingUser(null)}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleResetPasswordSave}
                disabled={!resetPasswordText.trim()}
                className="flex-1"
              >
                Commit Reset
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Absolute Deletion Confirmation Overlay */}
      {deletingUser && (
        <div className="frosted-glass-overlay">
          <div className="overlay-card card settings-card delete-warning-card">
            <h4 className="card-title danger" style={{ margin: 0, borderLeft: "3px solid #ef4444", paddingLeft: "8px", fontSize: "0.9rem" }}>
              <AlertTriangle size={16} style={{ color: "#ef4444", marginRight: "6px" }} />
              Purge Account Registry?
            </h4>
            <div className="deleted-info-box" style={{ marginTop: "16px", padding: "12px", background: "linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(239, 68, 68, 0.02) 100%)", border: "1px solid rgba(239, 68, 68, 0.2)", borderRadius: "8px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <UserX size={18} style={{ color: "#ef4444" }} />
                <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{deletingUser}</span>
              </div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "8px", lineHeight: "1.4" }}>
                Warning: Purging an account registry completely deletes their login profile. Historical session metadata and vector library operations authored by this identity will remain cataloged.
              </p>
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "20px" }}>
              <Button
                variant="secondary"
                onClick={() => setDeletingUser(null)}
                className="flex-1"
              >
                Keep Account
              </Button>
              <Button
                variant="destructive"
                onClick={handleDeleteConfirm}
                className="flex-1"
              >
                Purge Identity
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
