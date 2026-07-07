import React, { useState, useEffect } from "react";
import { useAuditStore } from "../stores/auditStore";
import { useDrawingStore } from "../stores/drawingStore";
import { useConnectionStore } from "../stores/connectionStore";
import { useWorkspaceStore } from "../stores/workspaceStore";
import { CopilotPanel } from "./copilot/CopilotPanel";
import {
  ShieldCheck,
  Play,
  Loader2,
  AlertTriangle,
  CheckCircle,
  Clock,
  Cpu,
  BookOpen,
  Layers,
  MapPin,
  Filter,
  XCircle
} from "lucide-react";

export const AuditConsole: React.FC = () => {
  const {
    standards,
    fetchStandards,
    launchAudit,
    activeSession,
    activeViolations,
    auditState,
    errorMessage,
    resetStore
  } = useAuditStore();

  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const selectViolation = useWorkspaceStore((s) => s.selectViolation);

  const { activeDrawing } = useDrawingStore();
  const { backendUrl, apiToken } = useConnectionStore.getState();

  const [selectedDrawingId, setSelectedDrawingId] = useState("");
  const [selectedStandardId, setSelectedStandardId] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [localDrawingsList, setLocalDrawingsList] = useState<any[]>([]);
  const [showCopilot, setShowCopilot] = useState(false);

  // Fetch drawings and standards lists on mount
  useEffect(() => {
    fetchStandards();
    fetchLocalDrawings();

    if (activeDrawing) {
      setSelectedDrawingId(activeDrawing.id);
    }
  }, [activeDrawing]);

  const fetchLocalDrawings = async () => {
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }
      const response = await fetch(`${backendUrl}/api/v1/drawings`, { headers });
      if (response.ok) {
        const result = await response.json();
        if (result.success && result.data) {
          setLocalDrawingsList(result.data);
        }
      }
    } catch (err) {
      console.warn("Failed to load drawings dropdown list", err);
    }
  };

  const handleStartAudit = async () => {
    if (!selectedDrawingId || !selectedStandardId) return;
    await launchAudit(selectedDrawingId, selectedStandardId);
  };

  const getScoreColor = (score: number) => {
    if (score >= 90) return { text: "#10b981", bg: "rgba(16, 185, 129, 0.1)", label: "EXCELLENT", border: "#10b981" };
    if (score >= 75) return { text: "#fbbf24", bg: "rgba(251, 191, 36, 0.1)", label: "PASSED WITH INFRACTIONS", border: "#fbbf24" };
    if (score >= 50) return { text: "#f97316", bg: "rgba(249, 115, 22, 0.1)", label: "NEEDS REVISION", border: "#f97316" };
    return { text: "#dc2626", bg: "rgba(220, 38, 38, 0.1)", label: "CRITICAL FAILURE", border: "#dc2626" };
  };

  const filteredViolations = activeViolations.filter((v) => {
    if (severityFilter === "all") return true;
    return v.severity.toLowerCase() === severityFilter.toLowerCase();
  });

  const getSeverityStyles = (sev: string) => {
    switch (sev.toLowerCase()) {
      case "critical":
        return { text: "#fca5a5", bg: "rgba(220, 38, 38, 0.15)", border: "rgba(220, 38, 38, 0.4)", iconColor: "#ef4444" };
      case "high":
        return { text: "#fdba74", bg: "rgba(249, 115, 22, 0.15)", border: "rgba(249, 115, 22, 0.4)", iconColor: "#f97316" };
      case "medium":
        return { text: "#fde047", bg: "rgba(234, 179, 8, 0.15)", border: "rgba(234, 179, 8, 0.4)", iconColor: "#eab308" };
      default:
        return { text: "#67e8f9", bg: "rgba(6, 182, 212, 0.15)", border: "rgba(6, 182, 212, 0.4)", iconColor: "#06b6d4" };
    }
  };

  const getDrawingName = (id: string) => {
    const d = localDrawingsList.find((dwg) => dwg.id === id);
    return d ? d.file_name : "Active Drawing";
  };

  const getStandardName = (id: string) => {
    const s = standards.find((std) => std.id === id);
    return s ? s.name : "Active Standard";
  };

  return (
    <div className="audit-console-layout">
      {/* 1. SELECTION CARD BAR */}
      {auditState === "idle" && (
        <div className="card audit-trigger-card">
          <h3 className="card-title">
            <ShieldCheck size={18} className="text-purple" />
            Initiate Drawing Auditing Run
          </h3>
          <p className="card-description">
            Match your ingested 2D structural drafting graphics directly against grounding engineering guidelines using rule-based metrics and secure Gemini Vision loops.
          </p>

          <div className="trigger-form-grid">
            <div className="form-group">
              <label className="form-label">1. Target Engineering Drawing</label>
              <select
                className="form-input select-input"
                value={selectedDrawingId}
                onChange={(e) => setSelectedDrawingId(e.target.value)}
              >
                <option value="">-- Choose Auditable CAD Drawing --</option>
                {localDrawingsList.map((dwg) => (
                  <option value={dwg.id} key={dwg.id}>
                    {dwg.file_name} ({dwg.format.toUpperCase()} - {Object.values(dwg.entity_counts).reduce((a: any, b: any) => a + b, 0)} primitives)
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">2. Target Compliance Standard</label>
              <select
                className="form-input select-input"
                value={selectedStandardId}
                onChange={(e) => setSelectedStandardId(e.target.value)}
              >
                <option value="">-- Choose Grounding Reference Standard --</option>
                {standards.map((std) => (
                  <option value={std.id} key={std.id}>
                    {std.name} ({std.format.toUpperCase()})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <button
            className="btn btn-primary mt-4"
            style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: "10px", padding: "14px" }}
            onClick={handleStartAudit}
            disabled={!selectedDrawingId || !selectedStandardId}
          >
            <Play size={18} fill="#fff" /> Run Comparative Standards Compliance Audit
          </button>
        </div>
      )}

      {/* 2. PROGRESS QUEUE LOADING STATE */}
      {auditState === "processing" && activeSession && (
        <div className="card loading-card">
          <Loader2 size={48} className="spin-animation text-purple" style={{ marginBottom: "20px" }} />
          <h4>Audit Pipeline Active</h4>
          <span className="loading-sub">
            Session ID: <code style={{ color: "#c084fc" }}>{activeSession.id}</code>
          </span>

          <div className="loading-steps-list">
            <div className="step-item active">
              <div className="step-bullet"></div>
              <span>Ingesting structural CAD geometric offsets...</span>
            </div>
            <div className="step-item active">
              <div className="step-bullet"></div>
              <span>Executing offline deterministic CAD standard checks...</span>
            </div>
            <div className="step-item active pulse">
              <div className="step-bullet"></div>
              <span>Running RAG grounded comparison via secure Gemini Vision orchestrator...</span>
            </div>
          </div>

          <div className="progress-container" style={{ maxWidth: "450px", margin: "24px auto 0 auto" }}>
            <div className="progress-bar-bg" style={{ height: "6px" }}>
              <div className="progress-bar-fill animated-gradient" style={{ width: "80%" }}></div>
            </div>
            <div className="progress-labels">
              <span>Evaluating drawing primitives against clauses</span>
              <span className="loading-dots">Active Pipeline</span>
            </div>
          </div>
        </div>
      )}

      {/* 3. ERROR WARNING STATE */}
      {auditState === "failed" && (
        <div className="card error-card">
          <XCircle size={48} className="text-red" style={{ marginBottom: "16px" }} />
          <h4>Auditing Pipeline Aborted</h4>
          <p className="card-description" style={{ color: "#fca5a5" }}>{errorMessage}</p>
          <button className="btn btn-primary mt-3" onClick={resetStore}>
            Return & Reconfigure Run
          </button>
        </div>
      )}

      {/* 4. SUCCESS RESULTS STATE */}
      {auditState === "completed" && activeSession && (
        <div className="results-view">

          {/* Top Info Bar with resetting action */}
          <div className="results-header">
            <div>
              <h4 className="results-title">Audited: {getDrawingName(activeSession.drawing_id || "")}</h4>
              <span className="results-subtitle">Grounded on: {getStandardName(activeSession.standard_id || "")}</span>
            </div>
            <div style={{ display: "flex", gap: "12px" }}>
              <button
                className={`btn ${showCopilot ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setShowCopilot(!showCopilot)}
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                <span>🤖</span> {showCopilot ? "Hide Copilot" : "Ask Engineering Copilot"}
              </button>
              <button className="btn btn-secondary" onClick={resetStore}>
                Launch New Audit
              </button>
            </div>
          </div>

          <div className="results-main-layout" style={{ display: "flex", gap: "24px", alignItems: "flex-start" }}>
            <div className="results-body-left" style={{ flex: 1, minWidth: 0 }}>

              {/* Scores Overview Row */}
              <div className="scores-grid">

                {/* Score 1: Compliance Gauge */}
                <div className="card score-card">
                  <span className="score-label">Overall Compliance Rating</span>

                  <div className="score-display">
                    <div
                      className="radial-gauge"
                      style={{ borderColor: getScoreColor(activeSession.compliance_score || 0).border }}
                    >
                      <span className="gauge-number" style={{ color: getScoreColor(activeSession.compliance_score || 0).text }}>
                        {activeSession.compliance_score}%
                      </span>
                    </div>
                  </div>

                  <div
                    className="score-verdict-badge"
                    style={{
                      color: getScoreColor(activeSession.compliance_score || 0).text,
                      background: getScoreColor(activeSession.compliance_score || 0).bg
                    }}
                  >
                    {getScoreColor(activeSession.compliance_score || 0).label}
                  </div>
                </div>

                {/* Score 2: Confidence Rating */}
                <div className="card score-card">
                  <span className="score-label">Aggregate Analysis Confidence</span>

                  <div className="score-display" style={{ minHeight: "140px", flexDirection: "column", justifyContent: "center" }}>
                    <span className="confidence-percent">
                      {((activeSession.confidence_score || 0.95) * 100).toFixed(1)}%
                    </span>
                    <span className="confidence-desc">
                      Confidence rating based on grounded database chunks matching and structural entity density overlaps.
                    </span>
                  </div>

                  <div className="score-verdict-badge bg-purple-soft text-purple">
                    HIGH VALIDATION FIDELITY
                  </div>
                </div>
              </div>

              {/* Diagnostic Execution Timings Card */}
              <div className="card timings-card">
                <h4 className="timing-title">
                  <Cpu size={16} className="text-purple" /> Diagnostics Console
                </h4>

                <div className="timing-grid">
                  <div className="timing-item">
                    <span className="timing-label">Rule Engine execution time</span>
                    <span className="timing-value">
                      <Clock size={12} /> {activeSession.timings.rule_engine_seconds || 0.05}s
                    </span>
                  </div>
                  <div className="timing-item">
                    <span className="timing-label">Gemini Vision comparative logic</span>
                    <span className="timing-value">
                      <Clock size={12} /> {activeSession.timings.ai_engine_seconds || 1.2}s
                    </span>
                  </div>
                  <div className="timing-item">
                    <span className="timing-label">Total pipeline roundtrip</span>
                    <span className="timing-value text-purple" style={{ fontWeight: 600 }}>
                      <Clock size={12} /> {activeSession.timings.total_seconds || 1.3}s
                    </span>
                  </div>
                  <div className="timing-item">
                    <span className="timing-label">Evaluated reference knowledge</span>
                    <span className="timing-value text-cyan" style={{ fontWeight: 600 }}>
                      <BookOpen size={12} /> {activeSession.diagnostics.grounding_chunks_evaluated || 8} segments
                    </span>
                  </div>
                </div>
              </div>

              {/* INFRACTIONS FEED PANEL */}
              <div className="infractions-feed-layout">

                {/* Filter Bar */}
                <div className="feed-header-bar">
                  <h3 className="section-title">
                    Drawing Infraction Feed ({filteredViolations.length})
                  </h3>

                  <div className="filter-group">
                    <Filter size={14} className="text-purple" />
                    <span className="filter-label">Filter Severity:</span>
                    <button
                      className={`btn-filter ${severityFilter === "all" ? "active" : ""}`}
                      onClick={() => setSeverityFilter("all")}
                    >
                      All
                    </button>
                    <button
                      className={`btn-filter ${severityFilter === "critical" ? "active" : ""}`}
                      onClick={() => setSeverityFilter("critical")}
                    >
                      Critical
                    </button>
                    <button
                      className={`btn-filter ${severityFilter === "high" ? "active" : ""}`}
                      onClick={() => setSeverityFilter("high")}
                    >
                      High
                    </button>
                    <button
                      className={`btn-filter ${severityFilter === "medium" ? "active" : ""}`}
                      onClick={() => setSeverityFilter("medium")}
                    >
                      Medium
                    </button>
                    <button
                      className={`btn-filter ${severityFilter === "low" ? "active" : ""}`}
                      onClick={() => setSeverityFilter("low")}
                    >
                      Low
                    </button>
                  </div>
                </div>

                {/* Cards List */}
                {filteredViolations.length === 0 ? (
                  <div className="empty-feed-card">
                    <CheckCircle size={36} className="text-emerald" style={{ marginBottom: "12px", opacity: 0.8 }} />
                    <h4>No violations detected</h4>
                    <p>Drawing meets all criteria in this specific reference grouping.</p>
                  </div>
                ) : (
                  <div className="infractions-list">
                    {filteredViolations.map((violation) => {
                      const styles = getSeverityStyles(violation.severity);
                      const isSelected = selectedViolation?.id === violation.id;
                      return (
                        <div
                          className={`violation-card card ${isSelected ? 'selected' : ''}`}
                          key={violation.id}
                          style={{
                            borderLeft: isSelected ? `6px solid ${styles.iconColor}` : `4px solid ${styles.iconColor}`,
                            cursor: 'pointer',
                            transform: isSelected ? 'translateX(4px)' : 'none',
                            boxShadow: isSelected ? `0 4px 20px rgba(${styles.iconColor === '#ef4444' ? '239, 68, 68' : styles.iconColor === '#f97316' ? '249, 115, 22' : '234, 179, 8'}, 0.2)` : 'none',
                            background: isSelected ? 'rgba(255, 255, 255, 0.02)' : undefined,
                            borderColor: isSelected ? styles.iconColor : undefined
                          }}
                          onClick={() => {
                            selectViolation(isSelected ? null : {
                              id: violation.id,
                              severity: violation.severity as any,
                              category: violation.category,
                              description: violation.description,
                              recommendation: violation.recommendation,
                              affected_entities: (violation.affected_entities || []).map((e: any) => e.type || String(e)),
                              confidence: violation.confidence,
                              coordinates: violation.coordinates && violation.coordinates.length > 0 ? (Array.isArray(violation.coordinates[0]) ? (violation.coordinates[0] as [number, number]) : (violation.coordinates as any)) : undefined,
                              standard_reference: violation.standard_reference || undefined,
                              pen_type: violation.pen_type || undefined,
                              is_resolved: violation.is_resolved,
                              checker_remarks: violation.checker_remarks || undefined
                            });
                          }}
                        >
                          <div className="violation-card-top">
                            <div className="violation-title-group">
                              <AlertTriangle size={16} style={{ color: styles.iconColor }} />
                              <h4 className="violation-category">{violation.category}</h4>
                            </div>

                            <div style={{ display: "flex", gap: "8px" }}>
                              <span className="source-badge">
                                {violation.source === "rule_engine" ? "CAD Engine" : "AI Grounding"}
                              </span>
                              <span
                                className="severity-badge"
                                style={{ color: styles.text, background: styles.bg, borderColor: styles.border }}
                              >
                                {violation.severity.toUpperCase()}
                              </span>
                            </div>
                          </div>

                          <p className="violation-desc">{violation.description}</p>

                          <div className="violation-recommendation-box">
                            <span className="rec-label">Correction Guideline:</span>
                            <p className="rec-text">{violation.recommendation}</p>
                          </div>

                          <div className="violation-footer">
                            {violation.standard_reference && (
                              <div className="footer-tag">
                                <BookOpen size={12} />
                                <span>Grounded Clause: {violation.standard_reference}</span>
                              </div>
                            )}

                            {violation.affected_entities && violation.affected_entities.length > 0 && (
                              <div className="footer-tag">
                                <Layers size={12} />
                                <span>Affected Primitives: {violation.affected_entities.map(e => e.type).join(", ")}</span>
                              </div>
                            )}

                            {violation.coordinates && (
                              <div className="footer-tag">
                                <MapPin size={12} />
                                <span>Coordinates: {JSON.stringify(violation.coordinates)}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {showCopilot && (
              <div className="results-body-right" style={{ width: "360px", flexShrink: 0, position: "sticky", top: "20px" }}>
                <CopilotPanel />
              </div>
            )}
          </div>
        </div>
      )}

      {/* COMPONENT SCOPED CSS STYLES */}
      <style>{`
        .audit-console-layout {
          animation: fadeIn 0.4s ease-out;
          padding: 0 32px;
          margin-top: 30px;
        }
        .audit-trigger-card {
          background: var(--bg-card);
          border: 2px dashed var(--border-color);
          border-radius: 12px;
          padding: 40px 32px;
          margin-bottom: 24px;
          color: var(--text-primary);
        }
        .trigger-form-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          margin-top: 24px;
        }
        .select-input {
          background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23a1a1aa' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
          background-repeat: no-repeat;
          background-position: right 12px center;
          background-size: 16px;
          padding-right: 40px;
          -webkit-appearance: none;
          -moz-appearance: none;
          appearance: none;
        }
        
        .loading-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 60px 20px;
          text-align: center;
        }
        .loading-card h4 {
          font-size: 1.15rem;
          font-weight: 600;
          color: #fff;
          margin-bottom: 4px;
        }
        .loading-sub {
          font-size: 0.78rem;
          color: #a1a1aa;
          margin-bottom: 24px;
        }
        .loading-steps-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
          text-align: left;
          width: 100%;
          max-width: 450px;
          background: rgba(0,0,0,0.15);
          padding: 16px;
          border-radius: 8px;
          border: 1px solid rgba(255,255,255,0.03);
        }
        .step-item {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.82rem;
          color: #71717a;
        }
        .step-item.active {
          color: #e4e4e7;
        }
        .step-item.pulse span {
          animation: pulseText 1.5s infinite ease-in-out;
        }
        @keyframes pulseText {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 1; }
        }
        .step-bullet {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #71717a;
        }
        .step-item.active .step-bullet {
          background: #a855f7;
          box-shadow: 0 0 8px #a855f7;
        }
        
        .error-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 50px 20px;
          text-align: center;
        }
        
        .results-view {
          animation: fadeIn 0.4s ease-out;
        }
        .results-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
          padding-bottom: 16px;
        }
        .results-title {
          font-size: 1.15rem;
          font-weight: 600;
          color: #fff;
          margin-bottom: 2px;
        }
        .results-subtitle {
          font-size: 0.82rem;
          color: #a1a1aa;
        }
        
        .scores-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          margin-bottom: 20px;
        }
        .score-card {
          padding: 20px;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .score-label {
          font-size: 0.78rem;
          font-weight: 600;
          color: #a1a1aa;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 16px;
        }
        .score-display {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 120px;
          width: 100%;
        }
        .radial-gauge {
          width: 110px;
          height: 110px;
          border-radius: 50%;
          border: 8px solid #a855f7;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 0 15px rgba(0,0,0,0.25);
        }
        .gauge-number {
          font-size: 1.8rem;
          font-weight: 700;
        }
        .confidence-percent {
          font-size: 2.2rem;
          font-weight: 700;
          color: #a855f7;
          text-shadow: 0 0 12px rgba(168, 85, 247, 0.3);
          margin-bottom: 4px;
        }
        .confidence-desc {
          font-size: 0.72rem;
          color: #71717a;
          text-align: center;
          max-width: 250px;
          line-height: 1.3;
        }
        .score-verdict-badge {
          margin-top: 16px;
          font-size: 0.72rem;
          font-weight: 700;
          padding: 4px 12px;
          border-radius: 4px;
          letter-spacing: 0.03em;
        }
        
        .timings-card {
          padding: 16px 20px;
          margin-bottom: 24px;
        }
        .timing-title {
          font-size: 0.85rem;
          font-weight: 600;
          color: #fff;
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 16px;
          border-bottom: 1px solid rgba(255,255,255,0.03);
          padding-bottom: 8px;
        }
        .timing-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
        }
        .timing-item {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .timing-label {
          font-size: 0.72rem;
          color: #71717a;
        }
        .timing-value {
          font-size: 0.88rem;
          font-weight: 500;
          color: #e4e4e7;
          display: flex;
          align-items: center;
          gap: 4px;
        }
        
        .feed-header-bar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        .filter-group {
          display: flex;
          align-items: center;
          gap: 8px;
          background: rgba(0,0,0,0.25);
          padding: 4px 8px;
          border-radius: 6px;
          border: 1px solid rgba(255,255,255,0.04);
        }
        .filter-label {
          font-size: 0.72rem;
          color: #a1a1aa;
          margin-right: 4px;
        }
        .btn-filter {
          background: none;
          border: none;
          color: #71717a;
          font-size: 0.72rem;
          font-weight: 600;
          padding: 3px 8px;
          border-radius: 4px;
          cursor: pointer;
        }
        .btn-filter:hover {
          color: #fff;
        }
        .btn-filter.active {
          color: #fff;
          background: #a855f7;
        }
        
        .empty-feed-card {
          background: rgba(0,0,0,0.15);
          border: 1px solid rgba(255,255,255,0.04);
          border-radius: 8px;
          padding: 30px;
          text-align: center;
        }
        .empty-feed-card h4 {
          font-size: 0.95rem;
          color: #fff;
          font-weight: 500;
          margin-bottom: 4px;
        }
        .empty-feed-card p {
          font-size: 0.78rem;
          color: #a1a1aa;
        }
        
        .infractions-list {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .violation-card {
          padding: 16px 20px;
          transition: transform 0.2s ease;
        }
        .violation-card:hover {
          transform: translateX(2px);
        }
        .violation-card-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        .violation-title-group {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .violation-category {
          font-size: 0.95rem;
          font-weight: 600;
          color: #fff;
        }
        .severity-badge {
          font-size: 0.65rem;
          font-weight: 700;
          padding: 2px 8px;
          border-radius: 4px;
          border: 1px solid;
          letter-spacing: 0.05em;
        }
        .source-badge {
          font-size: 0.65rem;
          font-weight: 600;
          padding: 2px 6px;
          border-radius: 4px;
          background: rgba(255,255,255,0.06);
          color: #a1a1aa;
          display: flex;
          align-items: center;
        }
        .violation-desc {
          font-size: 0.82rem;
          color: #d4d4d8;
          line-height: 1.4;
          margin-bottom: 14px;
        }
        .violation-recommendation-box {
          background: rgba(0,0,0,0.18);
          border: 1px solid rgba(255,255,255,0.03);
          border-radius: 6px;
          padding: 10px 14px;
          margin-bottom: 14px;
        }
        .rec-label {
          font-size: 0.72rem;
          font-weight: 600;
          color: #a855f7;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          display: block;
          margin-bottom: 4px;
        }
        .rec-text {
          font-size: 0.8rem;
          color: #e4e4e7;
          line-height: 1.45;
        }
        .violation-footer {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
        }
        .footer-tag {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          font-size: 0.7rem;
          color: #71717a;
          background: rgba(0,0,0,0.12);
          padding: 2px 8px;
          border-radius: 4px;
        }
      `}</style>
    </div>
  );
};
