import React, { useEffect, useState } from "react";
import { useAdminStore, EnterpriseUser } from "../../stores/adminStore";
import {
  UserPlus,
  Trash2,
  Shield,
  User,
  RefreshCw,
  Search,
  Key,
  Eye,
  EyeOff,
  Sparkles,
  X,
  Lock,
  CheckCircle2,
  AlertTriangle,
  UserCheck,
  UserX,
  Edit2
} from "lucide-react";

// Helper utility to parse ISO datetime strings from backend reliably as UTC
const parseUtcDate = (dateStr: string | null | undefined): Date => {
  if (!dateStr) return new Date();
  const utcStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  return new Date(utcStr);
};

export const UserManagement: React.FC = () => {
  const {
    users,
    isLoading,
    error: storeError,
    fetchUsers,
    createUser,
    deleteUser,
    updateUser
  } = useAdminStore();

  // Local state variables
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [showCreatePassword, setShowCreatePassword] = useState(false);

  // Searching / Filtering
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | "admin" | "user">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");

  // Reset password states
  const [resettingUser, setResettingUser] = useState<string | null>(null);
  const [resetPasswordText, setResetPasswordText] = useState("");
  const [showResetPassword, setShowResetPassword] = useState(false);

  // Edit user states
  const [editingUser, setEditingUser] = useState<EnterpriseUser | null>(null);
  const [editRole, setEditRole] = useState("user");

  // Success / Error toast indicators
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  // Confirmation overlay for destructive deletion
  const [deletingUser, setDeletingUser] = useState<string | null>(null);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Utility to generate dynamic random secure passwords
  const generateSecurePassword = () => {
    const chars = "abcdefghijklmnopqrstuvwxyz";
    const caps = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    const nums = "0123456789";
    const specs = "!@#$%^&*";
    let pass = "";
    for (let i = 0; i < 4; i++) pass += chars[Math.floor(Math.random() * chars.length)];
    for (let i = 0; i < 4; i++) pass += caps[Math.floor(Math.random() * caps.length)];
    for (let i = 0; i < 3; i++) pass += nums[Math.floor(Math.random() * nums.length)];
    pass += specs[Math.floor(Math.random() * specs.length)];
    return pass;
  };

  const handleGenerateCreatePassword = () => {
    const generated = generateSecurePassword();
    setNewPassword(generated);
    setShowCreatePassword(true);
    triggerNotification("Secure password generated successfully!");
  };

  const handleGenerateResetPassword = () => {
    const generated = generateSecurePassword();
    setResetPasswordText(generated);
    setShowResetPassword(true);
  };

  const triggerNotification = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(null), 4000);
  };

  const triggerError = (msg: string) => {
    setLocalError(msg);
    setTimeout(() => setLocalError(null), 4000);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword.trim()) return;

    const ok = await createUser(newUsername.trim(), newPassword, newRole);
    if (ok) {
      setNewUsername("");
      setNewPassword("");
      triggerNotification(`Account created successfully for: ${newUsername}`);
    } else {
      triggerError(storeError || "Failed to register enterprise account.");
    }
  };

  const handleToggleActive = async (username: string, currentActive: boolean) => {
    if (username === "admin") {
      triggerError("Cannot lock or deactivate the default system administrator.");
      return;
    }

    const ok = await updateUser(username, { active: !currentActive });
    if (ok) {
      triggerNotification(
        `User account ${username} successfully ${!currentActive ? "unlocked & activated" : "locked & suspended"}.`
      );
    } else {
      triggerError(storeError || "Failed to update account status.");
    }
  };

  const handleResetPasswordSave = async () => {
    if (!resettingUser || !resetPasswordText.trim()) return;

    const ok = await updateUser(resettingUser, { password: resetPasswordText.trim() });
    if (ok) {
      setResettingUser(null);
      setResetPasswordText("");
      triggerNotification(`Password successfully updated for user: ${resettingUser}`);
    } else {
      triggerError(storeError || "Failed to reset password.");
    }
  };

  const handleEditSave = async () => {
    if (!editingUser) return;
    if (editingUser.username === "admin" && editRole !== "admin") {
      triggerError("Cannot demote the default system administrator.");
      return;
    }

    const ok = await updateUser(editingUser.username, { role: editRole });
    if (ok) {
      setEditingUser(null);
      triggerNotification(`Account details successfully saved for: ${editingUser.username}`);
    } else {
      triggerError(storeError || "Failed to update account details.");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deletingUser) return;
    if (deletingUser === "admin") return;

    const ok = await deleteUser(deletingUser);
    if (ok) {
      triggerNotification(`Permanently purged user registry for: ${deletingUser}`);
    } else {
      triggerError(storeError || "Failed to delete account registry.");
    }
    setDeletingUser(null);
  };

  // Derive counts for real-time visual metrics dashboard
  const totalAccounts = users.length;
  const activeAccounts = users.filter((u) => u.active).length;
  const adminAccounts = users.filter((u) => u.role === "admin").length;
  const auditorAccounts = users.filter((u) => u.role === "user").length;

  // Filter users by client-side inputs
  const filteredUsers = users.filter((u) => {
    const matchesSearch = u.username.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesRole = roleFilter === "all" || u.role === roleFilter;
    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "active" && u.active) ||
      (statusFilter === "inactive" && !u.active);
    return matchesSearch && matchesRole && matchesStatus;
  });

  return (
    <div className="admin-subpage">
      {/* Dynamic Slide-Down Floating Toast Notifications */}
      {(successMessage || localError || storeError) && (
        <div className="admin-toast-container">
          {successMessage && (
            <div className="admin-toast success">
              <CheckCircle2 size={16} />
              <span>{successMessage}</span>
            </div>
          )}
          {localError && (
            <div className="admin-toast error">
              <AlertTriangle size={16} />
              <span>{localError}</span>
            </div>
          )}
        </div>
      )}

      {/* SUBPAGE HEADER */}
      <div className="subpage-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 className="section-title">User Account Registry</h2>
          <p className="section-desc">Add, authorize, suspend, or reset credentials for corporate enterprise engineers.</p>
        </div>
        <button
          className="btn btn-secondary refresh-directory-btn"
          onClick={() => fetchUsers()}
          disabled={isLoading}
          style={{ display: "flex", alignItems: "center", gap: "8px" }}
        >
          <RefreshCw size={14} className={isLoading ? "spin-animation" : ""} />
          Sync Directory
        </button>
      </div>

      {/* 1. VISUAL ANALYTICS METRICS STRIP (4 CARDS) */}
      <div className="admin-metrics-grid">
        <div className="card metrics-card">
          <div className="metrics-icon-wrapper blue">
            <User size={18} />
          </div>
          <div className="metrics-data">
            <span className="metrics-value">{totalAccounts}</span>
            <span className="metrics-label">Registered Accounts</span>
          </div>
        </div>

        <div className="card metrics-card">
          <div className="metrics-icon-wrapper green">
            <UserCheck size={18} />
          </div>
          <div className="metrics-data">
            <span className="metrics-value">{activeAccounts}</span>
            <span className="metrics-label">Active Directory</span>
          </div>
        </div>

        <div className="card metrics-card">
          <div className="metrics-icon-wrapper purple">
            <Shield size={18} />
          </div>
          <div className="metrics-data">
            <span className="metrics-value">{adminAccounts}</span>
            <span className="metrics-label">System Admins</span>
          </div>
        </div>

        <div className="card metrics-card">
          <div className="metrics-icon-wrapper cyan">
            <User size={18} />
          </div>
          <div className="metrics-data">
            <span className="metrics-value">{auditorAccounts}</span>
            <span className="metrics-label">Auditing Engineers</span>
          </div>
        </div>
      </div>

      {/* 2. SEARCH & MULTI-FILTER CONTROL PANEL */}
      <div className="card filter-control-card">
        <div className="filter-search-group">
          <div className="search-input-wrapper">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              placeholder="Search user directories by username..."
              className="form-input search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="clear-search-btn" onClick={() => setSearchQuery("")}>
                <X size={14} />
              </button>
            )}
          </div>

          <div className="filter-segments-wrapper">
            {/* Role Filters */}
            <div className="filter-pill-group">
              <span className="filter-pill-label">Role:</span>
              {(["all", "admin", "user"] as const).map((role) => (
                <button
                  key={role}
                  className={`filter-pill-btn ${roleFilter === role ? "active" : ""}`}
                  onClick={() => setRoleFilter(role)}
                >
                  {role === "all" ? "All Roles" : role === "admin" ? "Admins" : "Auditors"}
                </button>
              ))}
            </div>

            {/* Status Filters */}
            <div className="filter-pill-group">
              <span className="filter-pill-label">Status:</span>
              {(["all", "active", "inactive"] as const).map((status) => (
                <button
                  key={status}
                  className={`filter-pill-btn ${statusFilter === status ? "active" : ""}`}
                  onClick={() => setStatusFilter(status)}
                >
                  {status === "all" ? "All" : status === "active" ? "Active" : "Suspended"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 3. DUAL-GRID LAYOUT */}
      <div className="admin-grid-2" style={{ marginTop: "24px" }}>
        {/* Register New User Card */}
        <div className="card settings-card form-creation-card" style={{ display: "flex", flexDirection: "column" }}>
          <h3 className="card-title">
            <UserPlus size={18} style={{ color: "var(--accent-cyan)" }} />
            Register New Enterprise Account
          </h3>
          <p className="card-desc-text" style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "4px" }}>
            Add new personnel accounts to the secure local index.
          </p>

          <form onSubmit={handleCreate} className="admin-form" style={{ marginTop: "20px" }}>
            <div className="form-group">
              <label className="form-label">Username / login ID</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. j.doe"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                disabled={isLoading}
                required
              />
            </div>

            <div className="form-group">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <label className="form-label">Initial Password</label>
                <button
                  type="button"
                  className="pw-generate-link"
                  onClick={handleGenerateCreatePassword}
                  disabled={isLoading}
                >
                  <Sparkles size={12} />
                  Generate Secure
                </button>
              </div>
              <div className="input-icon-wrapper" style={{ position: "relative", display: "flex", alignItems: "center" }}>
                <input
                  type={showCreatePassword ? "text" : "password"}
                  className="form-input"
                  style={{ paddingRight: "40px" }}
                  placeholder="••••••••••••"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  disabled={isLoading}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowCreatePassword(!showCreatePassword)}
                  className="pw-toggle-visible-btn"
                >
                  {showCreatePassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Role Classification</label>
              <select
                className="form-input select-input"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                disabled={isLoading}
              >
                <option value="user">User (Auditing Engineer)</option>
                <option value="admin">Admin (System Administrator)</option>
              </select>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "12px" }}>
              <button
                type="submit"
                className="btn btn-primary create-account-submit-btn"
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
                disabled={isLoading}
              >
                <UserPlus size={16} />
                Register Account Credentials
              </button>
            </div>
          </form>
        </div>

        {/* Directory Listings Card */}
        <div className="card settings-card directory-listings-card" style={{ position: "relative", display: "flex", flexDirection: "column", marginTop: "24px" }}>
          {/* Frosted Glass Overlay for Editing User Details */}
          {editingUser && (
            <div className="frosted-glass-overlay">
              <div className="overlay-card card settings-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h4 className="card-title" style={{ margin: 0, borderLeft: "3px solid var(--accent-cyan)", paddingLeft: "8px", fontSize: "0.9rem" }}>
                    <Edit2 size={16} style={{ color: "var(--accent-cyan)", marginRight: "6px" }} />
                    Edit Enterprise Account
                  </h4>
                  <button className="btn-close-overlay" onClick={() => setEditingUser(null)}>
                    <X size={16} />
                  </button>
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
                  <button
                    className="btn btn-secondary"
                    onClick={() => setEditingUser(null)}
                    style={{ flex: 1, padding: "8px" }}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={handleEditSave}
                    disabled={isLoading}
                    style={{ flex: 1, padding: "8px" }}
                  >
                    Save Changes
                  </button>
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
                  <button className="btn-close-overlay" onClick={() => setResettingUser(null)}>
                    <X size={16} />
                  </button>
                </div>
                <p className="overlay-desc" style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "8px" }}>
                  Generating or entering a new password for account identity: <strong style={{ color: "var(--text-primary)" }}>{resettingUser}</strong>
                </p>

                <div className="form-group" style={{ marginTop: "16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <label className="form-label" style={{ margin: 0 }}>New Account Password</label>
                    <button
                      type="button"
                      className="pw-generate-link"
                      onClick={handleGenerateResetPassword}
                    >
                      <Sparkles size={12} />
                      Random Secure
                    </button>
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
                    <button
                      type="button"
                      onClick={() => setShowResetPassword(!showResetPassword)}
                      className="pw-toggle-visible-btn"
                    >
                      {showResetPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>

                <div style={{ display: "flex", gap: "12px", marginTop: "20px" }}>
                  <button
                    className="btn btn-secondary"
                    onClick={() => setResettingUser(null)}
                    style={{ flex: 1, padding: "8px" }}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={handleResetPasswordSave}
                    disabled={!resetPasswordText.trim()}
                    style={{ flex: 1, padding: "8px" }}
                  >
                    Commit Reset
                  </button>
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
                  <button
                    className="btn btn-secondary"
                    onClick={() => setDeletingUser(null)}
                    style={{ flex: 1, padding: "8px" }}
                  >
                    Keep Account
                  </button>
                  <button
                    className="btn btn-danger-confirm"
                    onClick={handleDeleteConfirm}
                    style={{ flex: 1, padding: "8px" }}
                  >
                    Purge Identity
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="card-title-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 className="card-title" style={{ margin: 0 }}>
              <Shield size={18} style={{ color: "var(--accent-cyan)" }} />
              Active System Users ({filteredUsers.length})
            </h3>
          </div>

          <div className="users-list-container" style={{ marginTop: "20px", flexGrow: 1, overflowY: "auto", minHeight: "0" }}>
            {filteredUsers.length === 0 ? (
              <div className="empty-state" style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)", border: "1px dashed var(--border-color)", borderRadius: "8px" }}>
                No enterprise users match the active search criteria.
              </div>
            ) : (
              <table className="stats-table">
                <thead>
                  <tr>
                    <th style={{ width: "35%", textAlign: "left", paddingBottom: "12px", color: "var(--text-muted)", fontSize: "0.8rem" }}>Account Identity</th>
                    <th style={{ width: "25%", textAlign: "left", paddingBottom: "12px", color: "var(--text-muted)", fontSize: "0.8rem" }}>Role</th>
                    <th style={{ width: "20%", textAlign: "center", paddingBottom: "12px", color: "var(--text-muted)", fontSize: "0.8rem" }}>Status</th>
                    <th style={{ width: "20%", textAlign: "right", paddingBottom: "12px", color: "var(--text-muted)", fontSize: "0.8rem" }}>Operations</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((userDoc) => (
                    <tr className={`stats-row ${!userDoc.active ? "suspended-row" : ""}`} key={userDoc.id}>
                      {/* Username Identity */}
                      <td className="stats-label" style={{ padding: "12px 8px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                          <div className={`user-icon-avatar ${userDoc.role}`}>
                            <User size={14} />
                          </div>
                          <div style={{ display: "flex", flexDirection: "column" }}>
                            <span className="user-table-username">{userDoc.username}</span>
                            <span className="user-table-date">Added {parseUtcDate(userDoc.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                          </div>
                        </div>
                      </td>

                      {/* Role Badge */}
                      <td className="stats-value" style={{ padding: "12px 8px", textAlign: "left" }}>
                        <span className={`role-badge ${userDoc.role}`}>
                          {userDoc.role.toUpperCase()}
                        </span>
                      </td>

                      {/* Active Toggle / Status Indicator */}
                      <td className="stats-value" style={{ textAlign: "center", padding: "12px 8px" }}>
                        <div style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                          {/* Pulse glowing dot */}
                          <span className={`status-pulse-dot ${userDoc.active ? "active" : "inactive"}`} />

                          {/* Suspend / Resume Button Switch */}
                          <button
                            className={`account-switch-btn ${userDoc.active ? "active" : "inactive"}`}
                            disabled={userDoc.username === "admin"}
                            onClick={() => handleToggleActive(userDoc.username, userDoc.active)}
                            title={userDoc.username === "admin" ? "Super Admin status is locked" : userDoc.active ? "Deactivate User" : "Activate User"}
                          >
                            <span className="account-switch-toggle-dot" />
                          </button>
                        </div>
                      </td>

                      {/* Operations: Edit / Reset Password / Delete User */}
                      <td className="stats-value" style={{ textAlign: "right", padding: "12px 8px" }}>
                        <div style={{ display: "inline-flex", gap: "8px", justifyContent: "flex-end" }}>
                          <button
                            className="btn-action-round edit-usr-btn"
                            onClick={() => {
                              setEditingUser(userDoc);
                              setEditRole(userDoc.role);
                            }}
                            title="Edit User Profile"
                          >
                            <Edit2 size={14} />
                          </button>

                          <button
                            className="btn-action-round reset-pw-btn"
                            onClick={() => {
                              setResettingUser(userDoc.username);
                              setResetPasswordText("");
                            }}
                            title="Reset User Password"
                          >
                            <Key size={14} />
                          </button>

                          <button
                            className="btn-action-round delete-usr-btn"
                            onClick={() => setDeletingUser(userDoc.username)}
                            disabled={userDoc.username === "admin" || isLoading}
                            title={userDoc.username === "admin" ? "Protected System Admin" : "Delete Account Registry"}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .admin-subpage {
          animation: fadeIn 0.4s ease-out;
        }

        /* 1. TOAST NOTIFICATIONS styling */
        .admin-toast-container {
          position: fixed;
          top: 24px;
          right: 24px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          z-index: 2000;
          pointer-events: none;
        }

        .admin-toast {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 20px;
          border-radius: 8px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
          font-size: 0.85rem;
          color: #ffffff;
          animation: slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          pointer-events: auto;
          border-left: 4px solid transparent;
        }

        .admin-toast.success {
          background: rgba(24, 24, 27, 0.95);
          border-left-color: #10b981;
          border: 1px solid rgba(16, 185, 129, 0.2);
          color: #10b981;
        }

        .admin-toast.error {
          background: rgba(24, 24, 27, 0.95);
          border-left-color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.2);
          color: #ef4444;
        }

        /* 2. METRICS STRIP */
        .admin-metrics-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
          margin-bottom: 24px;
        }

        .metrics-card.card {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 16px 20px !important;
          border: 1px solid var(--border-color);
          border-radius: 12px;
          background: var(--bg-card);
          transition: all 0.25s ease;
        }

        .metrics-card.card:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
          border-color: rgba(255, 255, 255, 0.1);
        }

        .metrics-icon-wrapper {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 42px;
          height: 42px;
          border-radius: 10px;
        }

        .metrics-icon-wrapper.blue { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
        .metrics-icon-wrapper.green { background: rgba(16, 185, 129, 0.1); color: #10b981; }
        .metrics-icon-wrapper.purple { background: rgba(168, 85, 247, 0.1); color: #a855f7; }
        .metrics-icon-wrapper.cyan { background: rgba(6, 182, 212, 0.1); color: #06b6d4; }

        .metrics-data {
          display: flex;
          flex-direction: column;
        }

        .metrics-value {
          font-size: 1.4rem;
          font-weight: 700;
          color: var(--text-primary);
          line-height: 1.1;
        }

        .metrics-label {
          font-size: 0.72rem;
          color: var(--text-muted);
          margin-top: 2px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        /* 3. FILTER BOARD */
        .filter-control-card.card {
          padding: 12px 16px !important;
          border-radius: 12px;
          background: var(--bg-card);
          border: 1px solid var(--border-color);
        }

        .filter-search-group {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 20px;
          flex-wrap: wrap;
        }

        .search-input-wrapper {
          position: relative;
          display: flex;
          align-items: center;
          flex-grow: 1;
          max-width: 420px;
        }

        .search-icon {
          position: absolute;
          left: 12px;
          color: var(--text-muted);
        }

        .search-input.form-input {
          width: 100%;
          padding-left: 36px;
          padding-right: 32px;
          background: rgba(255, 255, 255, 0.03);
        }

        .search-input.form-input:focus {
          background: rgba(255, 255, 255, 0.05);
          box-shadow: 0 0 10px rgba(0, 229, 255, 0.1);
        }

        .clear-search-btn {
          position: absolute;
          right: 12px;
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          align-items: center;
        }

        .clear-search-btn:hover {
          color: var(--text-primary);
        }

        .filter-segments-wrapper {
          display: flex;
          gap: 20px;
          align-items: center;
          flex-wrap: wrap;
        }

        .filter-pill-group {
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(0, 0, 0, 0.2);
          padding: 3px;
          border-radius: 8px;
          border: 1px solid var(--border-color);
        }

        .filter-pill-label {
          font-size: 0.72rem;
          color: var(--text-muted);
          padding: 0 8px;
          font-weight: 600;
          text-transform: uppercase;
        }

        .filter-pill-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          padding: 5px 12px;
          border-radius: 6px;
          font-size: 0.75rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .filter-pill-btn:hover {
          color: var(--text-primary);
        }

        .filter-pill-btn.active {
          background: rgba(255, 255, 255, 0.08);
          color: #00e5ff;
          box-shadow: 0 1px 2px rgba(0,0,0,0.2);
        }

        /* 4. PASSWORDS & INPUTS */
        .pw-generate-link {
          background: transparent;
          border: none;
          color: var(--accent-cyan);
          font-size: 0.72rem;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 2px 6px;
          border-radius: 4px;
        }

        .pw-generate-link:hover {
          text-decoration: underline;
          background: rgba(0, 229, 255, 0.05);
        }

        .pw-toggle-visible-btn {
          position: absolute;
          right: 12px;
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          align-items: center;
        }

        .pw-toggle-visible-btn:hover {
          color: var(--text-primary);
        }

        .create-account-submit-btn:hover {
          box-shadow: 0 0 15px rgba(0, 229, 255, 0.3);
        }

        /* 5. TABLE ELEMENTS & AVATARS */
        .user-icon-avatar {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          border: 1px solid var(--border-color);
        }

        .user-icon-avatar.admin {
          background: rgba(168, 85, 247, 0.1);
          color: #c084fc;
          border-color: rgba(168, 85, 247, 0.2);
        }

        .user-icon-avatar.user {
          background: rgba(0, 229, 255, 0.1);
          color: #22d3ee;
          border-color: rgba(0, 229, 255, 0.2);
        }

        .user-table-username {
          font-size: 0.85rem;
          font-weight: 600;
          color: var(--text-primary);
        }

        .user-table-date {
          font-size: 0.68rem;
          color: var(--text-muted);
          margin-top: 1px;
        }

        .role-badge {
          font-size: 0.68rem;
          font-weight: 700;
          padding: 2px 8px;
          border-radius: 4px;
          display: inline-block;
          letter-spacing: 0.3px;
        }

        .role-badge.admin {
          background: rgba(168, 85, 247, 0.15);
          color: #c084fc;
          border: 1px solid rgba(168, 85, 247, 0.3);
        }

        .role-badge.user {
          background: rgba(0, 229, 255, 0.15);
          color: #22d3ee;
          border: 1px solid rgba(0, 229, 255, 0.3);
        }

        .stats-row {
          transition: background-color 0.2s ease;
        }

        .stats-row:hover {
          background-color: rgba(255, 255, 255, 0.02);
        }

        .stats-row.suspended-row {
          opacity: 0.55;
        }

        /* Active Green Pulse Dot */
        .status-pulse-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          display: inline-block;
        }

        .status-pulse-dot.active {
          background: #10b981;
          box-shadow: 0 0 8px #10b981;
          position: relative;
        }

        .status-pulse-dot.inactive {
          background: #ef4444;
          box-shadow: none;
        }

        /* 6. SWITCH TOGGLE SLIDER */
        .account-switch-btn {
          width: 32px;
          height: 16px;
          border-radius: 10px;
          border: 1px solid var(--border-color);
          position: relative;
          cursor: pointer;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
          padding: 0;
          background: rgba(255, 255, 255, 0.05);
        }

        .account-switch-btn.active {
          background: rgba(16, 185, 129, 0.2);
          border-color: rgba(16, 185, 129, 0.5);
        }

        .account-switch-btn:disabled {
          cursor: not-allowed;
          opacity: 0.3;
        }

        .account-switch-toggle-dot {
          display: block;
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: #a1a1aa;
          position: absolute;
          top: 2px;
          left: 3px;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .account-switch-btn.active .account-switch-toggle-dot {
          left: 17px;
          background: #10b981;
          box-shadow: 0 0 6px #10b981;
        }

        /* 7. ACTION BUTTONS ROUND */
        .btn-action-round {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 28px;
          height: 28px;
          border-radius: 6px;
          background: transparent;
          border: 1px solid var(--border-color);
          color: var(--text-muted);
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .btn-action-round:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.05);
        }

        .btn-action-round.edit-usr-btn:hover {
          color: var(--accent-cyan);
          border-color: rgba(0, 229, 255, 0.3);
        }

        .btn-action-round.reset-pw-btn:hover {
          color: var(--accent-cyan);
          border-color: rgba(0, 229, 255, 0.3);
        }

        .btn-action-round.delete-usr-btn:hover {
          color: #ef4444;
          border-color: rgba(239, 68, 68, 0.3);
          background: rgba(239, 68, 68, 0.05);
        }

        .btn-action-round:disabled {
          cursor: not-allowed;
          opacity: 0.25;
        }

        /* 8. OVERLAYS & DIALOGS */
        .frosted-glass-overlay {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(9, 9, 11, 0.7);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
          z-index: 100;
          border-radius: 14px;
          animation: fadeIn 0.25s ease-out;
        }

        .overlay-card {
          width: 100%;
          max-width: 360px;
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          padding: 20px !important;
          box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
        }

        .btn-close-overlay {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 4px;
          border-radius: 4px;
          display: flex;
          align-items: center;
        }

        .btn-close-overlay:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.05);
        }

        /* Custom premium Danger confirm button */
        .btn-danger-confirm {
          background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #ffffff;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          box-shadow: 0 4px 12px rgba(239, 68, 68, 0.25);
        }

        .btn-danger-confirm:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(239, 68, 68, 0.45);
          background: linear-gradient(135deg, #f87171 0%, #dc2626 100%);
        }

        .btn-danger-confirm:active {
          transform: translateY(0);
        }

        @keyframes slideInRight {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }

        @media (max-width: 1200px) {
          .admin-metrics-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }

        @media (max-width: 768px) {
          .admin-metrics-grid {
            grid-template-columns: 1fr;
          }
          .filter-search-group {
            flex-direction: column;
            align-items: stretch;
          }
          .search-input-wrapper {
            max-width: none;
          }
        }
      `}</style>
    </div>
  );
};
