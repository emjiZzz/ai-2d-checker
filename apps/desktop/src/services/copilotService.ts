/**
 * Copilot Service — AI Engineering Assistant
 *
 * Wraps all communication with the backend AI Copilot streaming endpoint.
 * Provides context injection (active violation, drawing metadata, standards)
 * so the model always has relevant engineering context without the caller
 * needing to assemble it.
 */

import { streamApi } from "./fetchUtils";
import { useCopilotStore } from "../stores/copilotStore";
import { useWorkspaceStore } from "../stores/workspaceStore";
import { useAuditStore } from "../stores/auditStore";

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * Build the context block injected into every copilot message as system context.
 * Pulls from active workspace state — drawing metadata, selected violation,
 * and any active audit session diagnostics.
 */
function buildContextBlock(): string {
  const { newDrawing, violations, selectedViolation, complianceScore } = useWorkspaceStore.getState();
  const { activeSession, activeViolations } = useAuditStore.getState();

  const lines: string[] = ["[ENGINEERING CONTEXT]"];

  if (newDrawing) {
    lines.push(`Drawing: ${newDrawing.file_name} (${newDrawing.format.toUpperCase()})`);
    if (newDrawing.metadata?.acad_version) {
      lines.push(`AutoCAD Version: ${newDrawing.metadata.acad_version}`);
    }
    if (newDrawing.entity_counts) {
      const counts = Object.entries(newDrawing.entity_counts)
        .map(([k, v]) => `${v} ${k}s`)
        .join(", ");
      lines.push(`Extracted Entities: ${counts}`);
    }
  }

  const score = complianceScore ?? activeSession?.compliance_score;
  if (score !== null && score !== undefined) {
    lines.push(`Compliance Score: ${score}%`);
  }

  // Active selected violation takes priority
  const violation = selectedViolation ?? (activeViolations.length > 0 ? activeViolations[0] : null);
  if (violation) {
    lines.push(`[ACTIVE VIOLATION]`);
    lines.push(`Category: ${violation.category}`);
    lines.push(`Severity: ${violation.severity.toUpperCase()}`);
    lines.push(`Description: ${violation.description}`);
    lines.push(`Recommendation: ${violation.recommendation}`);
    if (violation.standard_reference) {
      lines.push(`Standard Reference: ${violation.standard_reference}`);
    }
    if (violation.confidence) {
      lines.push(`AI Confidence: ${(violation.confidence * 100).toFixed(0)}%`);
    }
  }

  const allViolations = violations.length > 0 ? violations : activeViolations;
  if (allViolations.length > 0 && !violation) {
    lines.push(`Total Violations Detected: ${allViolations.length}`);
    const critical = allViolations.filter((v) => v.severity === "critical").length;
    const high = allViolations.filter((v) => v.severity === "high").length;
    if (critical > 0) lines.push(`Critical: ${critical}`);
    if (high > 0) lines.push(`High: ${high}`);
  }

  return lines.join("\n");
}

/**
 * Send a message and stream the response back.
 * Writes chunks directly into the copilot store as they arrive.
 *
 * @returns The full assistant response string, or throws on failure.
 */
export async function sendCopilotMessage(userText: string): Promise<string> {
  const store = useCopilotStore.getState();
  const { messages } = store;



  // Build history payload (last 10 turns max to stay within context limits)
  const historyWindow = messages.slice(-10).map((m) => ({
    role: m.role,
    content: m.content,
  }));

  const contextBlock = buildContextBlock();

  const payload = {
    message: userText,
    context: contextBlock,
    history: historyWindow,
  };

  // Generate a stable streaming message ID
  const assistantMsgId = `assistant_${Date.now()}`;

  store.addMessage({
    id: assistantMsgId,
    role: "assistant",
    content: "",
    isStreaming: true,
    citations: [],
  });
  store.setThinking(true);

  let fullResponse = "";

  try {
    for await (const chunk of streamApi("/api/v1/copilot/stream", payload)) {
      if (typeof chunk === "string") {
        fullResponse += chunk;
        store.updateStreamingMessage(assistantMsgId, chunk);
      }
    }
  } catch (err: any) {
    // On stream failure, replace the empty streaming message with the error
    store.updateStreamingMessage(
      assistantMsgId,
      `⚠ Copilot error: ${err?.message || "Connection lost."}`
    );
    fullResponse = "";
  } finally {
    store.setThinking(false);
    // Mark streaming as done
    store.updateStreamingMessage(assistantMsgId, "");
  }

  return fullResponse;
}
