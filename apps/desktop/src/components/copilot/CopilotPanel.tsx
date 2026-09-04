import React, { useState, useRef, useEffect } from "react";
import { 
  Bot, 
  User, 
  Send, 
  Sparkles, 
  Trash2, 
  Copy, 
  Check, 
  FileCode2, 
  AlertTriangle, 
  Gauge, 
  Layers, 
  MessageSquare, 
  Lightbulb,
  ExternalLink
} from "lucide-react";
import { useCopilotStore } from "../../stores/copilotStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useAuditStore } from "../../stores/auditStore";
import { sendCopilotMessage } from "../../services/copilotService";
import { MarkdownRenderer } from "./MarkdownRenderer";

// ─── Sub-components ───────────────────────────────────────────────────────────

const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => {
  const getStyle = () => {
    switch (severity.toLowerCase()) {
      case "critical":
        return "bg-red-500/15 text-red-400 border-red-500/30";
      case "high":
        return "bg-orange-500/15 text-orange-400 border-orange-500/30";
      case "medium":
        return "bg-yellow-500/15 text-yellow-400 border-yellow-500/30";
      case "low":
        return "bg-blue-500/15 text-blue-400 border-blue-500/30";
      default:
        return "bg-zinc-500/15 text-zinc-400 border-zinc-500/30";
    }
  };

  return (
    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${getStyle()}`}>
      {severity}
    </span>
  );
};

const ContextBanner: React.FC = () => {
  const { newDrawing, selectedViolation, complianceScore } = useWorkspaceStore();
  const { activeSession } = useAuditStore();

  const score = complianceScore ?? activeSession?.compliance_score;

  if (!newDrawing && !selectedViolation) return null;

  return (
    <div className="bg-bg-card border border-border-color rounded-lg p-2.5 mb-3 text-xs flex flex-col gap-1.5 shrink-0 shadow-xs">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-accent-cyan flex items-center gap-1.5">
          <Layers size={12} className="text-accent-cyan" />
          Active Grounding Context
        </span>
        {score !== null && score !== undefined && (
          <span className="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30">
            Score: {score}%
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-text-muted">
        {newDrawing && (
          <span className="flex items-center gap-1 bg-bg-dark px-2 py-0.5 rounded border border-border-color text-text-primary font-mono truncate max-w-[180px]" title={newDrawing.file_name}>
            <FileCode2 size={11} className="text-accent-cyan shrink-0" />
            {newDrawing.file_name}
          </span>
        )}

        {selectedViolation && (
          <div className="flex items-center gap-1 bg-bg-dark px-2 py-0.5 rounded border border-border-color text-text-primary truncate max-w-[180px]">
            <SeverityBadge severity={selectedViolation.severity} />
            <span className="font-semibold truncate">
              {selectedViolation.category.replace(/_/g, " ")}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

// Renders chat bubble for user or assistant
const ChatBubble: React.FC<{
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}> = ({ role, content, isStreaming }) => {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div className="flex justify-end mb-3 group w-full">
        <div className="flex items-start gap-2 max-w-[85%]">
          <div className="flex flex-col items-end min-w-0">
            <div className="bg-bg-bubble-user border border-border-color text-text-primary rounded-xl rounded-tr-xs px-3.5 py-2.5 shadow-xs text-xs leading-relaxed break-words [overflow-wrap:anywhere] [word-break:break-word]">
              {content}
            </div>
            <span className="text-[10px] text-text-muted mt-1 mr-1">You</span>
          </div>
          <div className="w-6 h-6 rounded-md bg-bg-dark border border-border-color flex items-center justify-center text-text-muted shrink-0 mt-0.5">
            <User size={12} />
          </div>
        </div>
      </div>
    );
  }

  // Assistant Bubble
  return (
    <div className="flex justify-start mb-3.5 group w-full">
      <div className="flex items-start gap-2 w-full min-w-0">
        {/* Bot Avatar */}
        <div className="w-6 h-6 rounded-md bg-accent-cyan/10 border border-accent-cyan/30 flex items-center justify-center text-accent-cyan shrink-0 mt-0.5">
          <Bot size={13} />
        </div>

        {/* Bubble Card Container */}
        <div className="flex-1 flex flex-col min-w-0 w-full">
          <div className="flex items-center justify-between mb-1 px-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-bold text-accent-cyan">Engineering Copilot</span>
              <span className="text-[10px] text-text-muted">· CAD Grounded</span>
            </div>
            {content && !isStreaming && (
              <button
                onClick={handleCopy}
                className="opacity-0 group-hover:opacity-100 flex items-center gap-1 text-[10px] text-text-muted hover:text-text-primary transition-opacity cursor-pointer px-1.5 py-0.5 rounded hover:bg-bg-dark"
                title="Copy response"
              >
                {copied ? <Check size={11} className="text-emerald-500" /> : <Copy size={11} />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            )}
          </div>

          <div className="bg-bg-card border border-border-color hover:border-accent-cyan/40 rounded-xl rounded-tl-xs p-3.5 shadow-xs text-text-primary text-xs leading-relaxed transition-colors min-w-0 w-full break-words [overflow-wrap:anywhere] [word-break:break-word]">
            {content ? (
              <MarkdownRenderer content={content} />
            ) : null}

            {/* Thinking / Streaming Indicator */}
            {isStreaming && !content && (
              <div className="flex items-center gap-2 py-1 text-accent-cyan text-xs">
                <span className="inline-flex gap-1 items-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-bounce"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-bounce [animation-delay:0.2s]"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-bounce [animation-delay:0.4s]"></span>
                </span>
                <span className="text-text-muted text-[11px]">Reasoning over CAD geometry & standards...</span>
              </div>
            )}

            {/* Streaming Cursor */}
            {isStreaming && content && (
              <span className="inline-block w-1.5 h-3.5 bg-accent-cyan ml-1 align-text-bottom animate-pulse"></span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── Quick-prompt chips ───────────────────────────────────────────────────────

const QUICK_PROMPTS = [
  "Explain this violation and why it fails standard checks",
  "How do I remediate this issue in AutoCAD?",
  "What standard section does this geometry violate?",
  "What is the severity and production risk of this issue?",
];

// ─── Main Panel ───────────────────────────────────────────────────────────────

export const CopilotPanel: React.FC = () => {
  const { messages, addMessage, clearSession } = useCopilotStore();
  const [inputText, setInputText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [activeTab, setActiveTab] = useState<"chat" | "violations" | "insights">("chat");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { violations, selectedViolation, selectViolation, newDrawing } = useWorkspaceStore();
  const { activeViolations, activeSession } = useAuditStore();

  const allViolations = violations.length > 0 ? violations : activeViolations;

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, activeTab]);

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
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleViolationClick = (v: any) => {
    selectViolation(v);
    setActiveTab("chat");
    handleSend(`Explain this compliance violation and how to fix it in CAD: "${v.description || v.category}" (Standard: ${v.standard_reference || "General"})`);
  };

  return (
    <div className="flex flex-col h-full w-full bg-bg-sidebar text-text-primary box-border overflow-hidden">
      {/* Top Header */}
      <div className="flex justify-between items-center pb-2 mb-2 border-b border-border-color shrink-0">
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-5 rounded-md bg-accent-cyan/10 border border-accent-cyan/30 flex items-center justify-center text-accent-cyan">
            <Sparkles size={12} />
          </div>
          <h2 className="text-xs font-bold text-text-primary uppercase tracking-wide m-0">
            AI Engineering Copilot
          </h2>
        </div>
        <button
          onClick={clearSession}
          title="Clear conversation history"
          className="flex items-center gap-1 bg-transparent border border-border-color text-text-muted hover:text-text-primary hover:bg-bg-dark cursor-pointer text-[10px] py-0.5 px-2 rounded transition-all"
        >
          <Trash2 size={10} />
          <span>Clear</span>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-bg-dark border border-border-color rounded-lg mb-2.5 shrink-0">
        {(["chat", "violations", "insights"] as const).map((tab) => (
          <button
            key={tab}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 px-2 rounded-md text-xs font-semibold cursor-pointer transition-all ${
              activeTab === tab
                ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan shadow-xs"
                : "text-text-muted hover:text-text-primary hover:bg-sidebar-item-hover border border-transparent"
            }`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "chat" && <MessageSquare size={12} />}
            {tab === "violations" && <AlertTriangle size={12} />}
            {tab === "insights" && <Lightbulb size={12} />}
            <span>{tab === "chat" ? "Chat" : tab === "violations" ? "Violations" : "Insights"}</span>
            {tab === "violations" && allViolations.length > 0 && (
              <span className="bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.2 rounded-full leading-tight">
                {allViolations.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Scrollable Content Container */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden pr-0.5 min-h-0 w-full" ref={scrollRef}>
        {/* ── CHAT TAB ── */}
        {activeTab === "chat" && (
          <div className="flex flex-col w-full min-w-0">
            <ContextBanner />

            {messages.length === 0 && (
              <div className="text-center py-6 px-3 text-text-muted text-xs flex flex-col items-center justify-center gap-3 bg-bg-card border border-border-color rounded-lg w-full min-w-0 shadow-xs">
                <div className="w-10 h-10 rounded-lg bg-accent-cyan/10 border border-accent-cyan/30 flex items-center justify-center text-accent-cyan shadow-inner">
                  <Bot size={22} />
                </div>
                <div>
                  <div className="font-bold text-xs text-text-primary mb-1">
                    CAD Copilot Standing By
                  </div>
                  <div className="text-text-muted text-[11px] max-w-[260px] leading-relaxed">
                    Ask questions about standards, drawing geometry, BOM tables, or automated fix procedures.
                  </div>
                </div>

                {/* Quick prompts */}
                <div className="flex flex-col gap-1.5 w-full mt-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted text-left pl-1">
                    Suggested Questions
                  </span>
                  {QUICK_PROMPTS.map((p) => (
                    <button
                      key={p}
                      onClick={() => handleSend(p)}
                      disabled={isSending}
                      className="bg-bg-dark border border-border-color hover:border-accent-cyan/50 hover:bg-sidebar-item-hover text-text-primary text-[11px] p-2 rounded-md cursor-pointer text-left transition-all leading-normal flex items-center justify-between group"
                    >
                      <span className="truncate">{p}</span>
                      <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 transition-opacity text-accent-cyan shrink-0 ml-1" />
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
          </div>
        )}

        {/* ── VIOLATIONS TAB ── */}
        {activeTab === "violations" && (
          <div className="flex flex-col gap-2 w-full min-w-0">
            {allViolations.length === 0 ? (
              <div className="text-center py-10 text-text-muted text-xs bg-bg-card border border-border-color rounded-lg p-6">
                <AlertTriangle size={30} className="mx-auto mb-2 text-text-muted opacity-50" />
                <span>No compliance infractions detected yet. Execute an audit in Stage 2 Auditor first.</span>
              </div>
            ) : (
              allViolations.map((v) => {
                const isSelected = selectedViolation?.id === v.id;
                return (
                  <div
                    key={v.id}
                    onClick={() => handleViolationClick(v)}
                    className={`bg-bg-card border rounded-lg p-3 cursor-pointer transition-all duration-150 hover:border-accent-cyan/50 flex flex-col gap-1.5 w-full min-w-0 ${
                      isSelected ? "border-accent-cyan bg-accent-cyan/5 shadow-xs" : "border-border-color"
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <SeverityBadge severity={v.severity} />
                      <span className="text-[10px] font-mono text-text-muted">
                        {(v.confidence * 100).toFixed(0)}% conf
                      </span>
                    </div>

                    <h5 className="text-xs font-bold text-text-primary m-0">
                      {v.category.replace(/_/g, " ")}
                    </h5>
                    <p className="text-[11px] text-text-muted m-0 line-clamp-2 leading-relaxed">
                      {v.description}
                    </p>

                    <div className="flex justify-between items-center mt-1 pt-1.5 border-t border-border-color text-[10px]">
                      <span className="text-text-muted font-mono">
                        {v.standard_reference ? `§ ${v.standard_reference}` : "General"}
                      </span>
                      <span className="text-accent-cyan hover:underline font-semibold flex items-center gap-1">
                        Ask Copilot →
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* ── INSIGHTS TAB ── */}
        {activeTab === "insights" && (
          <div className="flex flex-col gap-2.5 w-full min-w-0">
            {/* Drawing stats */}
            {newDrawing ? (
              <div className="bg-bg-card border border-border-color rounded-lg p-3 flex flex-col gap-2 shadow-xs">
                <h4 className="text-xs font-bold text-text-primary uppercase tracking-wide flex items-center gap-1.5 m-0">
                  <FileCode2 size={12} className="text-accent-cyan" />
                  Drawing Entities Breakdown
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs mt-0.5">
                  {Object.entries(newDrawing.entity_counts || {}).map(([type, count]) => (
                    <div key={type} className="flex justify-between items-center bg-bg-dark p-2 rounded border border-border-color">
                      <span className="text-text-muted capitalize text-[11px]">{type}s</span>
                      <span className="font-mono font-bold text-accent-cyan">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="bg-bg-card border border-border-color rounded-lg p-4 text-xs text-text-muted text-center">
                Upload a revision drawing to see CAD entity metrics.
              </div>
            )}

            {/* Audit session summary */}
            {activeSession && (
              <div className="bg-bg-card border border-border-color rounded-lg p-3 flex flex-col gap-2 shadow-xs">
                <h4 className="text-xs font-bold text-text-primary uppercase tracking-wide flex items-center gap-1.5 m-0">
                  <Gauge size={12} className="text-accent-cyan" />
                  Audit Performance
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs mt-0.5">
                  <div className="flex justify-between items-center bg-bg-dark p-2 rounded border border-border-color">
                    <span className="text-text-muted text-[11px]">Compliance</span>
                    <span className="font-bold text-accent-cyan">{activeSession.compliance_score ?? "—"}%</span>
                  </div>
                  <div className="flex justify-between items-center bg-bg-dark p-2 rounded border border-border-color">
                    <span className="text-text-muted text-[11px]">Infractions</span>
                    <span className="font-bold text-orange-400">{allViolations.length}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Quick Action Analysis */}
            <div className="bg-bg-card border border-border-color rounded-lg p-3 flex flex-col gap-2 shadow-xs">
              <h4 className="text-xs font-bold text-accent-cyan m-0">AI Geometry Inspection</h4>
              <p className="text-[11px] text-text-muted m-0 leading-relaxed">
                Scan all layers and entities for structural inconsistencies or missing dimensions.
              </p>
              <button
                onClick={() => {
                  setActiveTab("chat");
                  handleSend("Perform a comprehensive CAD geometry inspection and summarize potential risks or structural concerns.");
                }}
                disabled={isSending || !newDrawing}
                className="w-full bg-accent-cyan text-on-accent text-xs font-semibold py-2 px-3 rounded-md cursor-pointer hover:brightness-110 transition-all disabled:opacity-50 disabled:pointer-events-none mt-1 shadow-xs"
              >
                Run AI Geometry Inspection
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Bottom Input Area */}
      <div className="mt-2 pt-2 border-t border-border-color shrink-0">
        <div className="flex gap-2 items-end bg-bg-dark border border-border-color rounded-lg p-1.5 focus-within:border-accent-cyan focus-within:shadow-[0_0_8px_rgba(0,229,255,0.15)] transition-all">
          <textarea
            ref={inputRef}
            rows={1}
            className="flex-1 bg-transparent border-0 resize-none text-xs text-text-primary focus:outline-none placeholder:text-text-muted max-h-20 py-1 px-1.5 leading-normal"
            placeholder={
              isSending ? "Copilot is reasoning..." : "Ask about standards, violations, or AutoCAD fix steps..."
            }
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSending}
          />
          <button
            onClick={() => handleSend()}
            disabled={isSending || !inputText.trim()}
            className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 transition-all cursor-pointer ${
              isSending || !inputText.trim()
                ? "bg-bg-dark text-text-muted opacity-40 cursor-not-allowed border border-border-color"
                : "bg-accent-cyan text-on-accent hover:brightness-110 shadow-xs"
            }`}
            title="Send message (Enter)"
          >
            <Send size={12} />
          </button>
        </div>
        <div className="text-[10px] text-text-muted mt-1 text-center flex items-center justify-center gap-1">
          <span>Enter to send · Shift+Enter for new line · Gemini & OpenAI</span>
        </div>
      </div>
    </div>
  );
};
