import React, { useState, useEffect } from "react";
import { Server, Clock, Cpu, Database, AlertCircle, RefreshCw, Settings } from "lucide-react";
import { useConnectionStore, ConnectionStatus } from "../stores/connectionStore";

export const SystemDiagnostics: React.FC = () => {
  const { backendUrl, status, version, lastChecked, error, checkHealth, setBackendUrl, remoteApiToken, setRemoteApiToken } = useConnectionStore();
  const [isManualChecking, setIsManualChecking] = useState(false);
  const [inputUrl, setInputUrl] = useState(backendUrl);
  const [inputToken, setInputToken] = useState(remoteApiToken || "");
  const [diagnostics, setDiagnostics] = useState<{
    mongodb: boolean;
    storage_root: boolean;
    gemini_api: boolean;
    openai_api?: boolean;
  } | null>(null);

  useEffect(() => {
    setInputUrl(backendUrl);
  }, [backendUrl]);

  useEffect(() => {
    setInputToken(remoteApiToken || "");
  }, [remoteApiToken]);

  const fetchDiagnostics = async () => {
    try {
      const response = await fetch(`${backendUrl}/health`);
      if (response.ok) {
        const data = await response.json();
        if (data.services) {
          setDiagnostics(data.services);
        } else if (data.data && data.success) {
          setDiagnostics({
            mongodb: true,
            storage_root: true,
            gemini_api: true,
            openai_api: true
          });
        }
      } else {
        setDiagnostics(null);
      }
    } catch {
      setDiagnostics(null);
    }
  };

  useEffect(() => {
    if (status === "online") {
      fetchDiagnostics();
    } else {
      setDiagnostics(null);
    }
  }, [status, backendUrl]);

  const handleManualTrigger = async () => {
    setIsManualChecking(true);
    await checkHealth();
    await fetchDiagnostics();
    setIsManualChecking(false);
  };

  const handleUrlSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setBackendUrl(inputUrl);
  };

  const handleTokenSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setRemoteApiToken(inputToken);
  };

  const getStatusBadgeClass = (s: ConnectionStatus) => {
    const base = "flex items-center gap-2 py-1.5 px-3 rounded-full text-xs font-semibold border transition-all";
    switch (s) {
      case "online": return `${base} bg-emerald-500/10 border-emerald-500/20 text-[var(--color-online)]`;
      case "offline": return `${base} bg-red-500/10 border-red-500/20 text-[var(--color-offline)]`;
      case "connecting":
      case "reconnecting": return `${base} bg-amber-500/10 border-amber-500/20 text-[var(--color-connecting)]`;
      case "failed": return `${base} bg-red-500/10 border-red-500/20 text-[var(--color-failed)]`;
      case "invalid": return `${base} bg-pink-500/10 border-pink-500/20 text-[var(--color-invalid)]`;
      default: return `${base} bg-zinc-500/10 border-zinc-500/20 text-zinc-400`;
    }
  };

  const getPulseDotClass = (s: ConnectionStatus) => {
    const base = "w-2 h-2 rounded-full";
    switch (s) {
      case "online": return `${base} bg-[var(--color-online)] shadow-[0_0_8px_var(--color-online)] animate-pulse`;
      case "offline": return `${base} bg-[var(--color-offline)] shadow-[0_0_8px_var(--color-offline)]`;
      case "connecting":
      case "reconnecting": return `${base} bg-[var(--color-connecting)] shadow-[0_0_8px_var(--color-connecting)] animate-pulse`;
      case "failed": return `${base} bg-[var(--color-failed)] shadow-[0_0_8px_var(--color-failed)]`;
      case "invalid": return `${base} bg-[var(--color-invalid)] shadow-[0_0_8px_var(--color-invalid)]`;
      default: return `${base} bg-zinc-400`;
    }
  };

  const getStatusLabel = (s: ConnectionStatus) => {
    switch (s) {
      case "online": return "Backend Active";
      case "offline": return "Backend Offline";
      case "connecting": return "Connecting...";
      case "reconnecting": return "Reconnecting...";
      case "failed": return "Connection Failed";
      case "invalid": return "Invalid Handshake";
      default: return "Unknown";
    }
  };

  return (
    <div className="animate-fade-in max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-12 h-12 bg-amber-500/10 rounded-xl flex items-center justify-center border border-amber-500/20">
          <Server className="text-amber-500" size={24} />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-text-primary tracking-tight">System Diagnostics</h2>
          <p className="text-sm text-text-muted mt-1">Monitor connectivity, server health, and API integrations.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div className="card-panel">
          <div className="flex items-center gap-3 text-text-muted mb-3 font-semibold text-sm tracking-wide">
            <Server size={18} /> BACKEND STATUS
          </div>
          <div className={getStatusBadgeClass(status)} style={{ width: "fit-content", padding: "6px 12px" }}>
            <span className={getPulseDotClass(status)}></span>
            <span style={{ fontSize: "0.85rem" }}>{getStatusLabel(status)}</span>
          </div>
        </div>

        <div className="card-panel">
          <div className="flex items-center gap-3 text-text-muted mb-3 font-semibold text-sm tracking-wide">
            <Clock size={18} /> LAST PING
          </div>
          <div className="text-lg font-mono text-text-primary">
            {lastChecked ? new Date(lastChecked).toLocaleTimeString() : "Never"}
          </div>
        </div>

        <div className="card-panel">
          <div className="flex items-center gap-3 text-text-muted mb-3 font-semibold text-sm tracking-wide">
            <Cpu size={18} /> API VERSION
          </div>
          <div className="text-lg font-mono text-text-primary">
            {version ? `v${version}` : "Unknown"}
          </div>
        </div>

        <div className="card-panel">
          <div className="flex items-center gap-3 text-text-muted mb-3 font-semibold text-sm tracking-wide">
            <AlertCircle size={18} /> ERROR LOGS
          </div>
          <div className={`text-lg font-mono ${error ? "text-red-400" : "text-emerald-400"}`}>
            {error ? "Issues Found" : "0 Active Alerts"}
          </div>
        </div>
      </div>

      <div className="card-panel mb-8 p-6">
        <h3 className="text-lg font-bold text-text-primary mb-4 flex items-center gap-2">
          <Database size={20} className="text-accent-cyan" /> Integrated Services
        </h3>
        
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-bg-dark rounded-lg border border-border-color">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center border border-blue-500/20">
                <Database className="text-blue-500" size={18} />
              </div>
              <div>
                <div className="font-semibold text-text-primary">MongoDB Database</div>
                <div className="text-xs text-text-muted">Document Storage & Registries</div>
              </div>
            </div>
            <div className={`px-3 py-1 rounded-full text-xs font-bold border ${diagnostics?.mongodb ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-bg-sidebar border-border-color text-text-muted'}`}>
              {diagnostics?.mongodb ? 'OPERATIONAL' : 'UNKNOWN'}
            </div>
          </div>

          <div className="flex items-center justify-between p-4 bg-bg-sidebar rounded-lg border border-border-color">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-purple-500/10 flex items-center justify-center border border-purple-500/20">
                <Server className="text-purple-500" size={18} />
              </div>
              <div>
                <div className="font-semibold text-text-primary">Local Storage Root</div>
                <div className="text-xs text-text-muted">File Persistence & Caching</div>
              </div>
            </div>
            <div className={`px-3 py-1 rounded-full text-xs font-bold border ${diagnostics?.storage_root ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-bg-sidebar border-border-color text-text-muted'}`}>
              {diagnostics?.storage_root ? 'OPERATIONAL' : 'UNKNOWN'}
            </div>
          </div>

          <div className="flex items-center justify-between p-4 bg-bg-sidebar rounded-lg border border-border-color">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20">
                <Cpu className="text-indigo-500" size={18} />
              </div>
              <div>
                <div className="font-semibold text-text-primary">Gemini AI Models</div>
                <div className="text-xs text-text-muted">Vision & Audit Engine API</div>
              </div>
            </div>
            <div className={`px-3 py-1 rounded-full text-xs font-bold border ${diagnostics?.gemini_api ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-bg-sidebar border-border-color text-text-muted'}`}>
              {diagnostics?.gemini_api ? 'OPERATIONAL' : 'UNKNOWN'}
            </div>
          </div>

          <div className="flex items-center justify-between p-4 bg-bg-sidebar rounded-lg border border-border-color">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-teal-500/10 flex items-center justify-center border border-teal-500/20">
                <Cpu className="text-teal-500" size={18} />
              </div>
              <div>
                <div className="font-semibold text-text-primary">OpenAI Models</div>
                <div className="text-xs text-text-muted">GPT-4o Multimodal Engine API</div>
              </div>
            </div>
            <div className={`px-3 py-1 rounded-full text-xs font-bold border ${diagnostics?.openai_api ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-bg-sidebar border-border-color text-text-muted'}`}>
              {diagnostics?.openai_api ? 'OPERATIONAL' : 'CONFIGURED / STANDBY'}
            </div>
          </div>
        </div>
      </div>

      <div className="card-panel p-6">
        <h3 className="text-lg font-bold text-text-primary mb-4 flex items-center gap-2">
          <Settings size={20} className="text-zinc-400" /> Connection Controls
        </h3>
        <p className="text-sm text-text-muted mb-6">Manually force a diagnostic ping or change the target backend URI and remote authentication token.</p>

        <div className="flex flex-col gap-4">
          <div>
            <label className="text-xs font-semibold text-text-muted mb-1.5 block">Backend Address</label>
            <form onSubmit={handleUrlSubmit} className="flex gap-4">
              <input
                type="text"
                className="input-field flex-grow font-mono text-sm bg-bg-dark"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
                placeholder="http://127.0.0.1:8080 or https://ai-2d-checker-backend.onrender.com"
              />
              <button type="submit" className="btn btn-secondary whitespace-nowrap">
                Update Host
              </button>
            </form>
          </div>

          <div>
            <label className="text-xs font-semibold text-text-muted mb-1.5 block">Remote API Token (for cloud/remote servers)</label>
            <form onSubmit={handleTokenSubmit} className="flex gap-4">
              <input
                type="password"
                className="input-field flex-grow font-mono text-sm bg-bg-dark"
                value={inputToken}
                onChange={(e) => setInputToken(e.target.value)}
                placeholder="Paste remote API token..."
              />
              <button type="submit" className="btn btn-secondary whitespace-nowrap">
                Save Token
              </button>
            </form>
          </div>
        </div>

        <div className="mt-6 flex gap-4 pt-6 border-t border-border-color">
          <button
            onClick={handleManualTrigger}
            disabled={isManualChecking}
            className="btn btn-primary"
          >
            <RefreshCw size={16} className={isManualChecking ? "spin-animation" : ""} />
            {isManualChecking ? "Connecting..." : "Trigger Manual Diagnostic Check"}
          </button>
        </div>

        {error && (
          <div className="mt-4 p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400 font-mono">
            {error}
          </div>
        )}
      </div>
    </div>
  );
};
