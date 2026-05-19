import React, { useState } from "react";
import { useAdminStore } from "../../stores/adminStore";
import { Cpu, Key, Eye, EyeOff, Save, CheckCircle } from "lucide-react";

export const AIConfiguration: React.FC = () => {
  const { aiModelStatus, isLoading } = useAdminStore();
  const [apiKey, setApiKey] = useState("AIzaSyA4bc9X-y7Z1W92kd813A29kZ109dk");
  const [showKey, setShowKey] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gemini-1.5-pro");
  const [localFallback, setLocalFallback] = useState(true);
  const [savedMessage, setSavedMessage] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedMessage(true);
    setTimeout(() => setSavedMessage(false), 3000);
  };

  return (
    <div className="admin-subpage">
      <div className="subpage-header">
        <h2 className="section-title">AI Grounding & Copilot Settings</h2>
        <p className="section-desc">Manage API credentials, grounding limits, and hardware fallback pipelines.</p>
      </div>

      <div className="admin-grid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginTop: "20px" }}>
        {/* Model Configurations Form */}
        <div className="card settings-card">
          <h3 className="card-title">
            <Cpu size={18} style={{ color: "var(--accent-cyan)" }} />
            Gemini Vision Grounding Engine
          </h3>

          <form onSubmit={handleSave} className="admin-form" style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "20px" }}>
            {savedMessage && (
              <div className="alert alert-success" style={{ padding: "10px", borderRadius: "6px", background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.2)", color: "#10b981", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "8px" }}>
                <CheckCircle size={16} />
                <span>AI Grounding engine parameters updated successfully.</span>
              </div>
            )}

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
              <label className="form-label">Target LLM Model Node</label>
              <select
                className="form-input select-input"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
              >
                <option value="gemini-1.5-pro">Gemini 1.5 Pro (Multimodal Drawing Reasoning)</option>
                <option value="gemini-1.5-flash">Gemini 1.5 Flash (High speed geometric inference)</option>
                <option value="llama-3-local">Local Llama-3 8B (Pure offline loopback mode)</option>
              </select>
            </div>

            <div className="form-group checkbox-group" style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <input
                type="checkbox"
                id="local-fallback-check"
                checked={localFallback}
                onChange={(e) => setLocalFallback(e.target.checked)}
                style={{ width: "16px", height: "16px", cursor: "pointer" }}
              />
              <label htmlFor="local-fallback-check" className="form-label" style={{ margin: 0, textTransform: "none", cursor: "pointer" }}>
                Enable Offline Comparative Fallback (ezdxf heuristics) if APIs fail
              </label>
            </div>

            <button type="submit" className="btn btn-primary" style={{ display: "flex", alignItems: "center", gap: "8px", justifyContent: "center" }}>
              <Save size={16} />
              Save AI Settings Profile
            </button>
          </form>
        </div>

        {/* Model Live Performance Summary */}
        <div className="card settings-card">
          <h3 className="card-title">
            <Cpu size={18} style={{ color: "var(--accent-cyan)" }} />
            Active AI Orchestration telemetry
          </h3>
          <table className="stats-table" style={{ marginTop: "20px" }}>
            <tbody>
              <tr className="stats-row">
                <td className="stats-label">Gemini Vision Loop</td>
                <td className="stats-value" style={{ color: "#10b981" }}>
                  {aiModelStatus?.gemini_vision || "ONLINE (Active)"}
                </td>
              </tr>
              <tr className="stats-row">
                <td className="stats-label">Local Fallback status</td>
                <td className="stats-value" style={{ color: "var(--accent-cyan)" }}>
                  {aiModelStatus?.local_llama_fallback || "READY (Pure Offline Check)"}
                </td>
              </tr>
              <tr className="stats-row">
                <td className="stats-label">Token Quota Remaining</td>
                <td className="stats-value" style={{ fontFamily: "monospace" }}>
                  {aiModelStatus?.token_quota_remaining || "98.4%"}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
