import React from "react";
import { UserPlus, Sparkles, EyeOff, Eye } from "lucide-react";
import { Button } from "../../../components/ui/Button";

interface UserRegistrationFormProps {
  handleCreate: (e: React.FormEvent) => void;
  newUsername: string;
  setNewUsername: (val: string) => void;
  newPassword: string;
  setNewPassword: (val: string) => void;
  newRole: string;
  setNewRole: (val: string) => void;
  showCreatePassword: boolean;
  setShowCreatePassword: (val: boolean) => void;
  handleGenerateCreatePassword: () => void;
  isLoading: boolean;
}

export const UserRegistrationForm: React.FC<UserRegistrationFormProps> = ({
  handleCreate,
  newUsername,
  setNewUsername,
  newPassword,
  setNewPassword,
  newRole,
  setNewRole,
  showCreatePassword,
  setShowCreatePassword,
  handleGenerateCreatePassword,
  isLoading
}) => {
  return (
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
            <Button
              type="button"
              variant="link"
              size="sm"
              className="text-xs text-blue-500 hover:text-blue-600 p-0 h-auto gap-1"
              onClick={handleGenerateCreatePassword}
              disabled={isLoading}
            >
              <Sparkles size={12} />
              Generate Secure
            </Button>
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
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
              onClick={() => setShowCreatePassword(!showCreatePassword)}
            >
              {showCreatePassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </Button>
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
          <Button
            type="submit"
            variant="primary"
            className="gap-2"
            disabled={isLoading}
          >
            <UserPlus size={16} />
            Register Account Credentials
          </Button>
        </div>
      </form>
    </div>
  );
};
