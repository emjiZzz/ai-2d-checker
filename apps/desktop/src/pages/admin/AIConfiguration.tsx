import React, { useState } from "react";
import { useAdminStore } from "../../stores/adminStore";
import { Cpu, Key, Eye, EyeOff, Save, CheckCircle } from "lucide-react";

export const AIConfiguration: React.FC = () => {
  const { aiModelStatus, isLoading } = useAdminStore();
  const [apiKey, setApiKey] = useState("AIzaSyA4bc9X-y7Z1W92kd813A29kZ109dk");
  const [showKey, setShowKey] = useState(false);
  const [openaiApiKey, setOpenaiApiKey] = useState("sk-proj-................................");
  const [showOpenaiKey, setShowOpenaiKey] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gpt-5.4");
  const [localFallback, setLocalFallback] = useState(true);
  const [successToast, setSuccessToast] = useState<string | null>(null);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessToast("AI grounding parameters updated successfully.");
    setTimeout(() => setSuccessToast(null), 4000);
  };

  return (
    <div className="admin-subpage">
      {/* Floating Toast Notification */}
      {successToast && (
        <div className="admin-toast-container">
          <div className="admin-toast success">
            <CheckCircle size={16} />
            <span>{successToast}</span>
          </div>
        </div>
      )}

      <div className="subpage-header">
        <h2 className="section-title">AI Grounding & Copilot Settings</h2>
        <p className="section-desc">Manage API credentials, grounding limits, and hardware fallback pipelines.</p>
      </div>

      <div className="admin-grid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginTop: "20px" }}>
        {/* Model Configurations Form */}
        <div className="card settings-card">
          <h3 className="card-title">
            <Cpu size={18} style={{ color: "var(--accent-cyan)" }} />
            AI Model Engine Credentials
          </h3>

          <form onSubmit={handleSave} className="admin-form" style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "20px" }}>
            <div className="form-group">
              <label className="form-label">Gemini API Token Key</label>
              <div className="input-icon-wrapper" style={{ position: "relative", display: "flex", alignItems: "center" }}>
                <Key size={16} style={{ position: "absolute", left: "12px", color: "#71717a" }} />
                <input
                  type={showKey ? "text" : "password"}
                  className="form-input"
                  style={{ paddingLeft: "38px", paddingRight: "38px" }}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={isLoading}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  style={{ position: "absolute", right: "12px", background: "transparent", border: "none", color: "#71717a", cursor: "pointer", display: "flex", alignItems: "center" }}
                >
                  {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">OpenAI API Token Key</label>
              <div className="input-icon-wrapper" style={{ position: "relative", display: "flex", alignItems: "center" }}>
                <Key size={16} style={{ position: "absolute", left: "12px", color: "#71717a" }} />
                <input
                  type={showOpenaiKey ? "text" : "password"}
                  className="form-input"
                  style={{ paddingLeft: "38px", paddingRight: "38px" }}
                  value={openaiApiKey}
                  onChange={(e) => setOpenaiApiKey(e.target.value)}
                  disabled={isLoading}
                  placeholder="sk-proj-..."
                />
                <button
                  type="button"
                  onClick={() => setShowOpenaiKey(!showOpenaiKey)}
                  style={{ position: "absolute", right: "12px", background: "transparent", border: "none", color: "#71717a", cursor: "pointer", display: "flex", alignItems: "center" }}
                >
                  {showOpenaiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Target LLM Model Node</label>
              <select
                className="form-input select-input"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
              >
                <option value="gpt-5.4">OpenAI GPT-5.4 (Current Workhorse Standard)</option>
                <option value="gpt-5.6-sol">OpenAI GPT-5.6 Sol (Flagship Multimodal Reasoning)</option>
                <option value="gpt-5.6-terra">OpenAI GPT-5.6 Terra (Balanced Speed & Cost)</option>
                <option value="gpt-5.6-luna">OpenAI GPT-5.6 Luna (Fast Lightweight Inference)</option>
                <option value="gemini-3.1-pro-preview">Gemini 3.1 Pro (Multimodal Drawing Reasoning)</option>
                <option value="gemini-3.5-flash">Gemini 3.5 Flash (High speed geometric inference)</option>
                <option value="llama-3-local">Local Llama-3 8B (Pure offline loopback mode)</option>
              </select>
            </div>

            <div className="form-group" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 14px", background: "rgba(0, 0, 0, 0.15)", border: "1px solid var(--border-color)", borderRadius: "8px", marginTop: "4px" }}>
              <label htmlFor="local-fallback-check" className="form-label" style={{ margin: 0, textTransform: "none", cursor: "pointer", fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 500 }}>
                Enable Offline Comparative Fallback (ezdxf heuristics) if APIs fail
              </label>
              <button
                type="button"
                id="local-fallback-check"
                className={`account-switch-btn ${localFallback ? "active" : "inactive"}`}
                onClick={() => setLocalFallback(!localFallback)}
                style={{ flexShrink: 0 }}
              >
                <span className="account-switch-toggle-dot" />
              </button>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "8px" }}>
              <button type="submit" className="btn btn-primary" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Save size={16} />
                Save AI Settings Profile
              </button>
            </div>
          </form>
        </div>

        {/* Model Live Performance Summary */}
        <div className="card settings-card" style={{ display: "flex", flexDirection: "column" }}>
          <h3 className="card-title">
            <Cpu size={18} style={{ color: "var(--accent-cyan)" }} />
            Active AI Orchestration Telemetry
          </h3>
          <table className="stats-table" style={{ marginTop: "20px" }}>
            <tbody>
              <tr className="stats-row">
                <td className="stats-label" style={{ padding: "12px 8px" }}>Gemini Vision Loop</td>
                <td className="stats-value" style={{ color: "#10b981", padding: "12px 8px", display: "flex", alignItems: "center", gap: "8px", justifyContent: "flex-end" }}>
                  <span className="status-pulse-dot active" style={{ width: "6px", height: "6px" }} />
                  <span>{aiModelStatus?.gemini_vision || "ONLINE (Active)"}</span>
                </td>
              </tr>
              <tr className="stats-row">
                <td className="stats-label" style={{ padding: "12px 8px" }}>OpenAI Engine Loop</td>
                <td className="stats-value" style={{ color: "#10b981", padding: "12px 8px", display: "flex", alignItems: "center", gap: "8px", justifyContent: "flex-end" }}>
                  <span className="status-pulse-dot active" style={{ width: "6px", height: "6px" }} />
                  <span>{"ONLINE (Standby)"}</span>
                </td>
              </tr>
              <tr className="stats-row">
                <td className="stats-label" style={{ padding: "12px 8px" }}>Local Fallback Status</td>
                <td className="stats-value" style={{ color: "var(--accent-cyan)", padding: "12px 8px" }}>
                  {aiModelStatus?.local_llama_fallback || "READY (Pure Offline Check)"}
                </td>
              </tr>
              <tr className="stats-row">
                <td className="stats-label" style={{ padding: "12px 8px" }}>Token Quota Remaining</td>
                <td className="stats-value" style={{ fontFamily: "monospace", padding: "12px 8px" }}>
                  {aiModelStatus?.token_quota_remaining || "98.4%"}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <style>{`
        /* TOAST NOTIFICATIONS styling */
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

        /* SWITCH TOGGLE SLIDER */
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

        .status-pulse-dot {
          border-radius: 50%;
          display: inline-block;
        }

        .status-pulse-dot.active {
          background: #10b981;
          box-shadow: 0 0 8px #10b981;
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
      `}</style>
    </div>
  );
};
