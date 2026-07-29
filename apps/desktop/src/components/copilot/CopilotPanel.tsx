import React, { useState, useRef, useEffect } from "react";
import { useCopilotStore } from "../../stores/copilotStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useAuditStore } from "../../stores/auditStore";
import { sendCopilotMessage } from "../../services/copilotService";

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
      `
      setIsSending(false);`
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
    <div className="flex flex-col h-[calc(100vh-200px)] bg-bg-card border border-border-color rounded-2xl p-5 backdrop-blur-md shadow-2xl text-text-primary animate-slide-in-right">
      {/* Header */}
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-[1.15rem] font-semibold text-text-primary flex items-center gap-2 pb-1.5 mb-2">
          <span>🤖</span> AI Engineering Copilot
        </h2>
        <button
          onClick={clearSession}
          title="Clear conversation"
          className="bg-transparent border-0 text-text-muted cursor-pointer text-[11px] py-1 px-2 rounded-md hover:bg-sidebar-item-hover transition-all"
        >
          Clear
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-4 border-b border-border-color pb-3">
        {(["chat", "violations", "insights"] as const).map((tab) => (
          <button
            key={tab}
            className={`flex-1 bg-sidebar-item-hover border border-border-color text-text-muted text-[11px] font-semibold py-2 px-3 rounded-lg cursor-pointer transition-all duration-200 hover:bg-sidebar-item-hover hover:text-text-primary ${activeTab === tab ? "bg-purple-600/15 border-purple-500/35 text-purple-400 shadow-[0_0_10px_rgba(168,85,247,0.1)]" : ""
              }`}
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
      <div className="flex-1 overflow-y-auto pr-1" ref={scrollRef}>
        {/* ── CHAT TAB ── */}
        {activeTab === "chat" && (
          <>
            <ContextBanner />

            {messages.length === 0 && (
              <div className="text-center py-6 text-text-muted text-xs flex flex-col items-center justify-center gap-2">
                <div className="text-3xl mb-1.5">🔍</div>
                <div className="font-bold text-text-primary mb-1">
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
            <div className="bg-sidebar-item-hover border border-border-color p-3 rounded-lg flex flex-col gap-2 mt-4">
              <h3 className="text-xs font-bold text-blue-400 m-0">AI Geometry Analysis</h3>
              <p className="text-xs text-text-muted m-0 leading-relaxed">Let the copilot analyze the drawing's structure and geometry patterns.</p>
              <button
                onClick={() =>
                  handleSend(
                    "Analyze the geometry patterns in this drawing and highlight any structural concerns."
                  )
                }
                disabled={isSending || !newDrawing}
                className="w-full bg-blue-600/15 border border-blue-600/30 text-blue-100 text-xs font-semibold py-2 px-3 rounded-md cursor-pointer hover:bg-blue-600/25 transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                Analyze Drawing Geometry
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="mt-4 pt-4 border-t border-border-color">
        <div className="flex gap-2 items-center">
          <input
            ref={inputRef}
            type="text"
            className="flex-1 bg-bg-dark border border-border-color rounded-lg py-2 px-3 text-xs text-text-primary focus:outline-none focus:border-purple-500 focus:shadow-[0_0_10px_rgba(168,85,247,0.25)] transition-all outline-none disabled:opacity-50"
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
            className={`border border-purple-500/40 rounded-lg text-white w-9 h-9 flex items-center justify-center shrink-0 transition-all text-base ${isSending || !inputText.trim()
                ? "bg-purple-600/15 cursor-not-allowed opacity-50"
                : "bg-purple-600 hover:brightness-110 cursor-pointer"
              }`}
          >
            {isSending ? "⏳" : "↑"}
          </button>
        </div>
        <div className="text-[10px] text-text-muted mt-1.5 text-center">
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
