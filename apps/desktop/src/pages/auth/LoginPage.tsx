import React, { useState } from "react";
import { useAuthStore } from "../../stores/authStore";
import { KeyRound, ShieldAlert, User, Cpu } from "lucide-react";

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { login, error, isLoading } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    await login(username.trim(), password);
  };

  return (
    <div className="login-viewport">
      <div className="login-card">
        {/* Technical Branding Header */}
        <div className="login-branding">
          <div className="branding-logo">
            <Cpu size={28} className="logo-icon" />
          </div>
          <h2 className="branding-title">AI-2D-Checker</h2>
          <span className="branding-subtitle">Enterprise CAD Compliance Platform</span>
        </div>

        {/* Credentials Form */}
        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="error-banner">
              <ShieldAlert size={16} style={{ flexShrink: 0 }} />
              <span>{error}</span>
            </div>
          )}

          <div className="form-group">
            <label className="form-label" htmlFor="username">
              Username or ID
            </label>
            <div className="input-icon-wrapper">
              <User size={16} className="input-icon" />
              <input
                id="username"
                type="text"
                className="form-input"
                placeholder="e.g. engineer"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">
              Security Password
            </label>
            <div className="input-icon-wrapper">
              <KeyRound size={16} className="input-icon" />
              <input
                id="password"
                type="password"
                className="form-input"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                required
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary login-btn"
            disabled={isLoading}
          >
            {isLoading ? "Authenticating session..." : "Initialize Portal Access"}
          </button>
        </form>

        {/* Enterprise Context Footer */}
        <div className="login-help-box">
          <p className="help-heading">Demo Workspace Access Accounts:</p>
          <div className="help-credentials-grid">
            <span className="help-label">Admin Role:</span>
            <code className="help-code">admin</code>
            <code className="help-code">admin123</code>

            <span className="help-label">Engineer Role:</span>
            <code className="help-code">engineer</code>
            <code className="help-code">engineer123</code>
          </div>
        </div>
      </div>

      <style>{`
        .login-viewport {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100vw;
          height: 100vh;
          background: #09090b;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          color: #e4e4e7;
          overflow: hidden;
        }

        .login-card {
          width: 100%;
          max-width: 420px;
          background: #18181b;
          border: 1px solid #27272a;
          border-radius: 12px;
          padding: 40px 32px;
          box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
          animation: slideUp 0.4s ease-out;
        }

        .login-branding {
          text-align: center;
          margin-bottom: 30px;
        }

        .branding-logo {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 56px;
          height: 56px;
          border-radius: 12px;
          background: rgba(0, 229, 255, 0.1);
          border: 1px solid rgba(0, 229, 255, 0.2);
          margin-bottom: 12px;
        }

        .logo-icon {
          color: #00e5ff;
        }

        .branding-title {
          font-size: 1.5rem;
          font-weight: 700;
          color: #ffffff;
          margin: 0;
          letter-spacing: -0.025em;
        }

        .branding-subtitle {
          font-size: 0.8rem;
          color: #a1a1aa;
        }

        .login-form {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .error-banner {
          display: flex;
          align-items: center;
          gap: 10px;
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.2);
          padding: 12px;
          border-radius: 6px;
          color: #fca5a5;
          font-size: 0.85rem;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .form-label {
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          color: #a1a1aa;
          letter-spacing: 0.05em;
        }

        .input-icon-wrapper {
          position: relative;
          display: flex;
          align-items: center;
        }

        .input-icon {
          position: absolute;
          left: 12px;
          color: #71717a;
        }

        .form-input {
          width: 100%;
          padding: 10px 12px 10px 38px;
          background: #09090b;
          border: 1px solid #27272a;
          border-radius: 6px;
          color: #ffffff;
          font-size: 0.9rem;
          transition: all 0.2s ease;
        }

        .form-input:focus {
          border-color: #00e5ff;
          outline: none;
          box-shadow: 0 0 0 2px rgba(0, 229, 255, 0.15);
        }

        .login-btn {
          margin-top: 10px;
          padding: 12px;
          font-weight: 600;
          background: #00e5ff !important;
          color: #09090b !important;
          border: none !important;
          width: 100%;
        }

        .login-btn:hover {
          background: #33ebff !important;
          color: #09090b !important;
          transform: translateY(-1px);
        }

        .login-help-box {
          margin-top: 30px;
          padding-top: 20px;
          border-top: 1px solid #27272a;
          font-size: 0.75rem;
        }

        .help-heading {
          font-weight: 600;
          color: #a1a1aa;
          margin-bottom: 8px;
        }

        .help-credentials-grid {
          display: grid;
          grid-template-columns: 80px 1fr 1fr;
          gap: 6px;
          align-items: center;
        }

        .help-label {
          color: #71717a;
        }

        .help-code {
          font-family: monospace;
          background: #09090b;
          padding: 2px 6px;
          border-radius: 4px;
          color: #00e5ff;
          text-align: center;
        }

        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
};
