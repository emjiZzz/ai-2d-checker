import React, { useState, useRef, useEffect } from "react";
import { useCopilotStore } from "../../stores/copilotStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useAuditStore } from "../../stores/auditStore";
import { sendCopilotMessage } from "../../services/copilotService";
import "./CopilotPanel.css";

// ─── Sub-components ───────────────────────────────────────────────────────────

const SeverityDot: React.FC<{ severity: string }> = ({ severity }) => {
  const colors: Record<string, string> = {
    critical: "#ef4444",
    high: "#f97316",
    medium: "#fbbf24",
    low: "#60a5fa",
  };
  return (
    <span
      style={{
        display: "inline-block",
        width: 7,
        height: 7,
        borderRadius: "50%",
        background: colors[severity] ?? "#a1a1aa",
        marginRight: 6,
        flexShrink: 0,
      }}
    />
  );
};

const ContextBanner: React.FC = () => {
  const { newDrawing, selectedViolation, complianceScore } = useWorkspaceStore();
  const { activeSession } = useAuditStore();

  const score = complianceScore ?? activeSession?.compliance_score;

  if (!newDrawing && !selectedViolation) return null;

  return (
    <div
      style={{
        background: "rgba(124,58,237,0.08)",
        border: "1px solid rgba(124,58,237,0.2)",
        borderRadius: 10,
        padding: "10px 12px",
        marginBottom: 14,
        fontSize: "0.72rem",
        color: "#c4b5fd",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <span style={{ fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "#a78bfa" }}>
        Active Context
      </span>
      {newDrawing && (
        <span>📐 {newDrawing.file_name} ({newDrawing.format.toUpperCase()})</span>
      )}
      {score !== null && score !== undefined && (
        <span>🎯 Compliance: {score}%</span>
      )}
      {selectedViolation && (
        <span style={{ display: "flex", alignItems: "center" }}>
          <SeverityDot severity={selectedViolation.severity} />
          {selectedViolation.category.replace(/_/g, " ")}
        </span>
      )}
    </div>
  );
};

// Renders a single chat bubble with markdown-light formatting (bold, code, newlines)
const ChatBubble: React.FC<{ role: "user" | "assistant"; content: string; isStreaming?: boolean }> = ({
  role,
  content,
  isStreaming,
}) => {
  const isUser = role === "user";

  // Very lightweight inline renderer: bold (**text**) and inline code (`code`)
  const renderContent = (text: string) => {
    const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return (
          <code
            key={i}
            style={{
              fontFamily: "monospace",
              background: "rgba(255,255,255,0.08)",
              padding: "1px 5px",
              borderRadius: 4,
              fontSize: "0.9em",
            }}
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      // Preserve line breaks
      return part.split("\n").map((line, j) => (
        <React.Fragment key={`${i}-${j}`}>
          {line}
          {j < part.split("\n").length - 1 && <br />}
        </React.Fragment>
      ));
    });
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 10,
      }}
    >
      {!isUser && (
        <div
          style={{
            width: 26,
            height: 26,
            borderRadius: "50%",
            background: "rgba(124,58,237,0.2)",
            border: "1px solid rgba(124,58,237,0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "0.65rem",
            color: "#c084fc",
            flexShrink: 0,
            marginRight: 8,
            marginTop: 2,
          }}
        >
          AI
        </div>
      )}
      <div
        className={`chat-bubble ${role}`}
        style={{
          maxWidth: "82%",
          position: "relative",
        }}
      >
        {content ? renderContent(content) : null}
        {isStreaming && !content && (
          <span
            style={{
              display: "inline-flex",
              gap: 3,
              alignItems: "center",
              height: 16,
              padding: "0 2px",
            }}
          >
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: "50%",
                  background: "#a78bfa",
                  animation: `copilotDot 1.2s ease-in-out ${i * 0.2}s infinite`,
                  display: "inline-block",
                }}
              />
            ))}
          </span>
        )}
        {isStreaming && content && (
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 14,
              background: "#c084fc",
              marginLeft: 2,
              verticalAlign: "text-bottom",
              animation: "copilotCursor 0.7s step-end infinite",
            }}
          />
        )}
      </div>
    </div>
  );
};

// ─── Quick-prompt chips ───────────────────────────────────────────────────────

const QUICK_PROMPTS = [
  "Explain this violation in simple terms",
  "What standard section does this violate?",
  "How do I fix this in AutoCAD?",
  "What is the severity impact on production?",
];

// ─── Main Panel ───────────────────────────────────────────────────────────────

export const CopilotPanel: React.FC = () => {
  const { messages, addMessage, clearSession } = useCopilotStore();
  const [inputText, setInputText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [activeTab, setActiveTab] = useState<"chat" | "violations" | "insights">("chat");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { violations, selectedViolation, selectViolation, newDrawing } = useWorkspaceStore();
  const { activeViolations, activeSession } = useAuditStore();

  const allViolations = violations.length > 0 ? violations : activeViolations;

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async (text?: string) => {
    const msg = (text ?? inputText).trim();
    if (!msg || isSending) return;

    setInputText("");
    setIsSending(true);

    addMessage({
      id: `user_${Date.now()}`,
      role: "user",
      content: msg,
      isStreaming: false,
      citations: [],
    });

    try {
      await sendCopilotMessage(msg);
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleViolationClick = (v: any) => {
    selectViolation(v);
    setActiveTab("chat");
    handleSend(`Explain this violation and how to fix it: ${v.description}`);
  };

  return (
    <div className="copilot-panel">
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <h2 style={{ margin: 0 }}>
          <span>🤖</span> AI Engineering Copilot
        </h2>
        <button
          onClick={clearSession}
          title="Clear conversation"
          style={{
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            fontSize: "0.7rem",
            padding: "4px 8px",
            borderRadius: 6,
          }}
        >
          Clear
        </button>
      </div>

      {/* Tabs */}
      <div className="copilot-tabs">
        {(["chat", "violations", "insights"] as const).map((tab) => (
          <button
            key={tab}
            className={`copilot-tab-btn ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
            style={{ position: "relative" }}
          >
            {tab === "violations" && allViolations.length > 0 && (
              <span
                style={{
                  position: "absolute",
                  top: -4,
                  right: -4,
                  background: "#ef4444",
                  color: "#fff",
                  borderRadius: "50%",
                  width: 16,
                  height: 16,
                  fontSize: "0.6rem",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 700,
                }}
              >
                {allViolations.length}
              </span>
            )}
            {tab === "chat" ? "Chat" : tab === "violations" ? "Violations" : "Insights"}
          </button>
        ))}
      </div>

      {/* Scroll area */}
      <div className="copilot-scroll-area" ref={scrollRef}>
        {/* ── CHAT TAB ── */}
        {activeTab === "chat" && (
          <>
            <ContextBanner />

            {messages.length === 0 && (
              <div
                style={{
                  textAlign: "center",
                  padding: "24px 0",
                  color: "var(--text-muted)",
                  fontSize: "0.78rem",
                }}
              >
                <div style={{ fontSize: "2rem", marginBottom: 10 }}>🔍</div>
                <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
                  Engineering Copilot Ready
                </div>
                <div>Ask about violations, standards, or drawing geometry.</div>

                {/* Quick prompts */}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    marginTop: 20,
                    alignItems: "stretch",
                  }}
                >
                  {QUICK_PROMPTS.map((p) => (
                    <button
                      key={p}
                      onClick={() => handleSend(p)}
                      disabled={isSending}
                      style={{
                        background: "rgba(124,58,237,0.06)",
                        border: "1px solid rgba(124,58,237,0.18)",
                        borderRadius: 8,
                        color: "#c4b5fd",
                        fontSize: "0.72rem",
                        padding: "8px 12px",
                        cursor: "pointer",
                        textAlign: "left",
                        transition: "all 0.15s ease",
                      }}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <ChatBubble
                key={msg.id}
                role={msg.role}
                content={msg.content}
                isStreaming={msg.isStreaming}
              />
            ))}
          </>
        )}

        {/* ── VIOLATIONS TAB ── */}
        {activeTab === "violations" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {allViolations.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "40px 0",
                  color: "var(--text-muted)",
                  fontSize: "0.8rem",
                }}
              >
                No violations detected yet. Run an audit first.
              </div>
            ) : (
              allViolations.map((v) => {
                const isSelected = selectedViolation?.id === v.id;
                const sevColors: Record<string, string> = {
                  critical: "#ef4444",
                  high: "#f97316",
                  medium: "#fbbf24",
                  low: "#60a5fa",
                };
                const color = sevColors[v.severity] ?? "#a1a1aa";
                return (
                  <div
                    key={v.id}
                    onClick={() => handleViolationClick(v)}
                    style={{
                      background: isSelected
                        ? `rgba(${v.severity === "critical" ? "239,68,68" : v.severity === "high" ? "249,115,22" : "124,58,237"},0.1)`
                        : "rgba(255,255,255,0.02)",
                      border: `1px solid ${isSelected ? color : "rgba(255,255,255,0.06)"}`,
                      borderRadius: 10,
                      padding: "10px 12px",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: 5,
                      }}
                    >
                      <span
                        style={{
                          fontSize: "0.65rem",
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          color,
                          background: `${color}20`,
                          border: `1px solid ${color}40`,
                          padding: "2px 7px",
                          borderRadius: 20,
                        }}
                      >
                        {v.severity}
                      </span>
                      <span
                        style={{
                          fontSize: "0.62rem",
                          color: "var(--text-muted)",
                          fontFamily: "monospace",
                        }}
                      >
                        {(v.confidence * 100).toFixed(0)}% conf.
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: "var(--text-primary)",
                        fontWeight: 500,
                        marginBottom: 4,
                      }}
                    >
                      {v.category.replace(/_/g, " ")}
                    </div>
                    <div
                      style={{
                        fontSize: "0.7rem",
                        color: "var(--text-muted)",
                        lineHeight: 1.4,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {v.description}
                    </div>
                    {v.standard_reference && (
                      <div
                        style={{
                          fontSize: "0.62rem",
                          color: "#818cf8",
                          marginTop: 5,
                          fontFamily: "monospace",
                        }}
                      >
                        § {v.standard_reference}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* ── INSIGHTS TAB ── */}
        {activeTab === "insights" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Drawing stats */}
            {newDrawing ? (
              <div className="geometry-insight-card">
                <h3>Drawing Overview</h3>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "6px 12px",
                    fontSize: "0.72rem",
                  }}
                >
                  {Object.entries(newDrawing.entity_counts).map(([type, count]) => (
                    <React.Fragment key={type}>
                      <span style={{ color: "var(--text-muted)", textTransform: "capitalize" }}>
                        {type}s
                      </span>
                      <span style={{ color: "#10b981", fontWeight: 600, fontFamily: "monospace" }}>
                        {count}
                      </span>
                    </React.Fragment>
                  ))}
                </div>
              </div>
            ) : (
              <div className="geometry-insight-card">
                <p>No drawing loaded. Upload a DWG or DXF to see geometry insights.</p>
              </div>
            )}

            {/* Audit session summary */}
            {activeSession && (
              <div className="geometry-insight-card">
                <h3>Audit Session Summary</h3>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "6px 12px",
                    fontSize: "0.72rem",
                  }}
                >
                  <span style={{ color: "var(--text-muted)" }}>Compliance</span>
                  <span
                    style={{
                      fontWeight: 700,
                      color:
                        (activeSession.compliance_score ?? 0) >= 90
                          ? "#10b981"
                          : (activeSession.compliance_score ?? 0) >= 75
                          ? "#fbbf24"
                          : "#ef4444",
                    }}
                  >
                    {activeSession.compliance_score ?? "—"}%
                  </span>
                  <span style={{ color: "var(--text-muted)" }}>Confidence</span>
                  <span style={{ fontWeight: 600, color: "#60a5fa" }}>
                    {activeSession.confidence_score ?? "—"}%
                  </span>
                  <span style={{ color: "var(--text-muted)" }}>Violations</span>
                  <span style={{ fontWeight: 600, color: "#f97316" }}>
                    {allViolations.length}
                  </span>
                  {activeSession.timings?.total_seconds && (
                    <>
                      <span style={{ color: "var(--text-muted)" }}>Duration</span>
                      <span style={{ fontFamily: "monospace", color: "var(--text-primary)" }}>
                        {activeSession.timings.total_seconds.toFixed(2)}s
                      </span>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Ask copilot about insights */}
            <div className="geometry-insight-card">
              <h3>AI Geometry Analysis</h3>
              <p>Let the copilot analyze the drawing's structure and geometry patterns.</p>
              <button
                onClick={() =>
                  handleSend(
                    "Analyze the geometry patterns in this drawing and highlight any structural concerns."
                  )
                }
                disabled={isSending || !newDrawing}
              >
                Analyze Drawing Geometry
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="copilot-input-container">
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            ref={inputRef}
            type="text"
            className="copilot-input"
            placeholder={
              isSending ? "Copilot is thinking..." : "Ask about standards, violations, or geometry..."
            }
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSending}
          />
          <button
            onClick={() => handleSend()}
            disabled={isSending || !inputText.trim()}
            style={{
              background:
                isSending || !inputText.trim()
                  ? "rgba(124,58,237,0.15)"
                  : "rgba(124,58,237,0.8)",
              border: "1px solid rgba(124,58,237,0.4)",
              borderRadius: 8,
              color: "#fff",
              width: 36,
              height: 36,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: isSending || !inputText.trim() ? "not-allowed" : "pointer",
              flexShrink: 0,
              transition: "all 0.15s ease",
              fontSize: "1rem",
            }}
          >
            {isSending ? "⏳" : "↑"}
          </button>
        </div>
        <div
          style={{
            fontSize: "0.62rem",
            color: "var(--text-muted)",
            marginTop: 6,
            textAlign: "center",
          }}
        >
          Enter to send · Powered by Gemini Flash · Context-aware
        </div>
      </div>

      {/* Scoped keyframe animations */}
      <style>{`
        @keyframes copilotDot {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1.0); opacity: 1; }
        }
        @keyframes copilotCursor {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
};
