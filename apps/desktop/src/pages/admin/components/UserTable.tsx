import React from "react";
import { User, Trash2, Edit2, Key } from "lucide-react";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { EnterpriseUser } from "../../../stores/adminStore";

const parseUtcDate = (dateStr: string | null | undefined): Date => {
  if (!dateStr) return new Date();
  const utcStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  return new Date(utcStr);
};

export interface UserTableProps {
  filteredUsers: EnterpriseUser[];
  isLoading: boolean;
  handleToggleActive: (username: string, currentActive: boolean) => void;
  setEditingUser: (user: EnterpriseUser) => void;
  setEditRole: (role: string) => void;
  setResettingUser: (username: string) => void;
  setResetPasswordText: (text: string) => void;
  setDeletingUser: (username: string) => void;
}

export const UserTable: React.FC<UserTableProps> = ({
  filteredUsers,
  isLoading,
  handleToggleActive,
  setEditingUser,
  setEditRole,
  setResettingUser,
  setResetPasswordText,
  setDeletingUser,
}) => {
  if (filteredUsers.length === 0) {
    return (
      <div className="users-list-container" style={{ marginTop: "20px", flexGrow: 1, overflowY: "auto", minHeight: "0" }}>
        <div className="empty-state" style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)", border: "1px dashed var(--border-color)", borderRadius: "8px" }}>
          No enterprise users match the active search criteria.
        </div>
      </div>
    );
  }

  return (
    <div className="users-list-container" style={{ marginTop: "20px", flexGrow: 1, overflowY: "auto", minHeight: "0" }}>
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
                <Badge variant={userDoc.role === "admin" ? "warning" : "default"}>
                  {userDoc.role.toUpperCase()}
                </Badge>
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
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => {
                      setEditingUser(userDoc);
                      setEditRole(userDoc.role);
                    }}
                    title="Edit User Profile"
                  >
                    <Edit2 size={14} />
                  </Button>

                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => {
                      setResettingUser(userDoc.username);
                      setResetPasswordText("");
                    }}
                    title="Reset User Password"
                  >
                    <Key size={14} />
                  </Button>

                  <Button
                    variant="destructive"
                    size="icon"
                    onClick={() => setDeletingUser(userDoc.username)}
                    disabled={userDoc.username === "admin" || isLoading}
                    title={userDoc.username === "admin" ? "Protected System Admin" : "Delete Account Registry"}
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
