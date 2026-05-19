import React, { useEffect, useState } from "react";
import { useAdminStore } from "../../stores/adminStore";
import { UserPlus, Trash2, Shield, User, RefreshCw } from "lucide-react";

export const UserManagement: React.FC = () => {
  const { users, isLoading, error, fetchUsers, createUser, deleteUser } = useAdminStore();
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword.trim()) return;

    const ok = await createUser(newUsername.trim(), newPassword, newRole);
    if (ok) {
      setNewUsername("");
      setNewPassword("");
      setSuccessMessage(`Account created successfully for: ${newUsername}`);
      setTimeout(() => setSuccessMessage(null), 3000);
    }
  };

  const handleDelete = async (username: string) => {
    if (username === "admin") return;
    if (confirm(`Are you sure you want to delete the user: ${username}?`)) {
      await deleteUser(username);
    }
  };

  return (
    <div className="admin-subpage">
      <div className="subpage-header">
        <h2 className="section-title">User Account Registry</h2>
        <p className="section-desc">Add, authorize, or revoke active directory engineer credentials.</p>
      </div>

      <div className="admin-grid-2">
        {/* Create User Card */}
        <div className="card settings-card">
          <h3 className="card-title">
            <UserPlus size={18} style={{ color: "var(--accent-cyan)" }} />
            Register New Enterprise Account
          </h3>

          <form onSubmit={handleCreate} className="admin-form">
            {successMessage && (
              <div className="alert alert-success" style={{ margin: "10px 0", padding: "10px", borderRadius: "6px", background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.2)", color: "#10b981", fontSize: "0.85rem" }}>
                {successMessage}
              </div>
            )}
            {error && (
              <div className="alert alert-error" style={{ margin: "10px 0", padding: "10px", borderRadius: "6px", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.2)", color: "#ef4444", fontSize: "0.85rem" }}>
                {error}
              </div>
            )}

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
              <label className="form-label">Initial Password</label>
              <input
                type="password"
                className="form-input"
                placeholder="••••••••••••"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                disabled={isLoading}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Role Classification</label>
              <select
                className="form-input select-input"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                disabled={isLoading}
              >
                <option value="user">User (Engineer / Auditor)</option>
                <option value="admin">Admin (System Administrator)</option>
              </select>
            </div>

            <button type="submit" className="btn btn-primary" style={{ marginTop: "10px" }} disabled={isLoading}>
              Create Enterprise Account
            </button>
          </form>
        </div>

        {/* Users List Card */}
        <div className="card settings-card">
          <div className="card-title-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 className="card-title" style={{ margin: 0 }}>
              <Shield size={18} style={{ color: "var(--accent-cyan)" }} />
              Active System Users
            </h3>
            <button className="btn-icon-only" onClick={() => fetchUsers()} title="Refresh Directory">
              <RefreshCw size={14} className={isLoading ? "spin-animation" : ""} />
            </button>
          </div>

          <div className="users-list-container" style={{ marginTop: "20px" }}>
            {users.length === 0 ? (
              <div className="empty-state">No enterprise users found.</div>
            ) : (
              <table className="stats-table">
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", paddingBottom: "10px", color: "var(--text-muted)", fontSize: "0.8rem" }}>Account Identity</th>
                    <th style={{ textAlign: "left", paddingBottom: "10px", color: "var(--text-muted)", fontSize: "0.8rem" }}>Role</th>
                    <th style={{ textAlign: "right", paddingBottom: "10px", color: "var(--text-muted)", fontSize: "0.8rem" }}>Operations</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr className="stats-row" key={user.id}>
                      <td className="stats-label" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <User size={14} style={{ color: user.role === "admin" ? "#a855f7" : "#00e5ff" }} />
                        <span>{user.username}</span>
                      </td>
                      <td className="stats-value">
                        <span className={`role-badge ${user.role}`}>
                          {user.role.toUpperCase()}
                        </span>
                      </td>
                      <td className="stats-value" style={{ textAlign: "right" }}>
                        <button
                          className="btn-delete"
                          onClick={() => handleDelete(user.username)}
                          disabled={user.username === "admin" || isLoading}
                          title={user.username === "admin" ? "Protected System Admin" : "Delete Account"}
                          style={{ background: "transparent", border: "none", color: user.username === "admin" ? "#3f3f46" : "#ef4444", cursor: user.username === "admin" ? "not-allowed" : "pointer", padding: "4px" }}
                        >
                          <Trash2 size={16} />
                        </button>
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
        .subpage-header {
          margin-bottom: 24px;
        }
        .admin-grid-2 {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 24px;
        }
        .admin-form {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-top: 20px;
        }
        .role-badge {
          font-size: 0.7rem;
          font-weight: 700;
          padding: 2px 6px;
          border-radius: 4px;
          display: inline-block;
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
        .btn-icon-only {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 6px;
          border-radius: 4px;
          display: flex;
          align-items: center;
        }
        .btn-icon-only:hover {
          color: var(--accent-cyan);
        }
      `}</style>
    </div>
  );
};
