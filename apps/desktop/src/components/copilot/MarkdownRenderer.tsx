import React, { useState } from "react";
import { Copy, Check, Terminal } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
}

/**
 * Preprocesses markdown text to ensure inline headers and list items
 * separated without newlines are cleanly formatted on separate lines.
 */
function preprocessMarkdown(raw: string): string {
  if (!raw) return "";
  let text = raw;
  // If headers like "### Heading" or "#### Heading" are attached to previous text without a newline, insert a newline
  text = text.replace(/([^\n])(#{1,4}\s*)/g, "$1\n\n$2");
  // If numbered list items like "1. Item" or "2. Item" are attached without a newline
  text = text.replace(/([^\n])(\d+\.\s+)/g, "$1\n$2");
  // If bullet list items like "- Item" are attached without a newline
  text = text.replace(/([^\n])(-\s+)/g, "$1\n$2");
  return text;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  if (!content) return null;

  const normalized = preprocessMarkdown(content);

  // Split by code blocks first
  const blocks = normalized.split(/(```[\s\S]*?```)/g);

  return (
    <div className="flex flex-col gap-2 text-xs leading-relaxed text-text-primary w-full min-w-0 break-words [overflow-wrap:anywhere] [word-break:break-word]">
      {blocks.map((block, blockIdx) => {
        if (block.startsWith("```") && block.endsWith("```")) {
          // Code block
          const match = block.match(/^```(\w*)\n?([\s\S]*?)```$/);
          const lang = match ? match[1] : "";
          const code = match ? match[2] : block.slice(3, -3);
          return <CodeBlock key={blockIdx} code={code.trim()} language={lang} />;
        }

        // Regular markdown text (headers, lists, paragraphs)
        return <TextBlock key={blockIdx} text={block} />;
      })}
    </div>
  );
};

const CodeBlock: React.FC<{ code: string; language?: string }> = ({ code, language }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-2 rounded-lg border border-border-color bg-bg-dark overflow-hidden shadow-xs w-full min-w-0">
      <div className="flex items-center justify-between px-3 py-1.5 bg-bg-sidebar border-b border-border-color text-[10px] text-text-secondary font-mono">
        <div className="flex items-center gap-1.5">
          <Terminal size={12} className="text-accent-cyan" />
          <span>{language || "code"}</span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-text-muted hover:text-text-primary cursor-pointer transition-colors"
          title="Copy code"
        >
          {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-[11px] font-mono text-text-primary leading-normal m-0 whitespace-pre break-normal">
        {code}
      </pre>
    </div>
  );
};

const TextBlock: React.FC<{ text: string }> = ({ text }) => {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let currentList: { type: "ul" | "ol"; items: React.ReactNode[] } | null = null;

  const flushList = () => {
    if (currentList) {
      if (currentList.type === "ul") {
        elements.push(
          <ul key={`list-${elements.length}`} className="my-1.5 pl-4 list-disc space-y-1 text-text-primary w-full min-w-0">
            {currentList.items.map((item, idx) => (
              <li key={idx} className="leading-relaxed pl-0.5 break-words [overflow-wrap:anywhere]">
                {item}
              </li>
            ))}
          </ul>
        );
      } else {
        elements.push(
          <ol key={`list-${elements.length}`} className="my-1.5 pl-4 list-decimal space-y-1 text-text-primary w-full min-w-0">
            {currentList.items.map((item, idx) => (
              <li key={idx} className="leading-relaxed pl-0.5 break-words [overflow-wrap:anywhere]">
                {item}
              </li>
            ))}
          </ol>
        );
      }
      currentList = null;
    }
  };

  lines.forEach((line, lineIdx) => {
    const trimmed = line.trim();

    if (!trimmed) {
      flushList();
      return;
    }

    // Headers
    if (trimmed.startsWith("#### ")) {
      flushList();
      elements.push(
        <h5 key={`h4-${lineIdx}`} className="text-[11px] font-bold text-accent-cyan mt-2 mb-0.5 uppercase tracking-wide break-words [overflow-wrap:anywhere]">
          {renderInlineFormatting(trimmed.slice(5))}
        </h5>
      );
      return;
    }
    if (trimmed.startsWith("### ")) {
      flushList();
      elements.push(
        <h4 key={`h3-${lineIdx}`} className="text-xs font-bold text-accent-cyan mt-2.5 mb-1 flex items-center gap-1.5 uppercase tracking-wide break-words [overflow-wrap:anywhere]">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan inline-block shrink-0"></span>
          <span>{renderInlineFormatting(trimmed.slice(4))}</span>
        </h4>
      );
      return;
    }
    if (trimmed.startsWith("## ")) {
      flushList();
      elements.push(
        <h3 key={`h2-${lineIdx}`} className="text-xs font-bold text-text-primary mt-3 mb-1 border-b border-border-color pb-1 break-words [overflow-wrap:anywhere]">
          {renderInlineFormatting(trimmed.slice(3))}
        </h3>
      );
      return;
    }
    if (trimmed.startsWith("# ")) {
      flushList();
      elements.push(
        <h2 key={`h1-${lineIdx}`} className="text-sm font-extrabold text-text-primary mt-3 mb-1.5 break-words [overflow-wrap:anywhere]">
          {renderInlineFormatting(trimmed.slice(2))}
        </h2>
      );
      return;
    }

    // Bullet list items (- or *)
    const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (bulletMatch) {
      if (!currentList || currentList.type !== "ul") {
        flushList();
        currentList = { type: "ul", items: [] };
      }
      currentList.items.push(renderInlineFormatting(bulletMatch[1]));
      return;
    }

    // Numbered list items (e.g. 1. or 2.)
    const numberMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (numberMatch) {
      if (!currentList || currentList.type !== "ol") {
        flushList();
        currentList = { type: "ol", items: [] };
      }
      currentList.items.push(renderInlineFormatting(numberMatch[2]));
      return;
    }

    // Standard paragraph
    flushList();
    elements.push(
      <p key={`p-${lineIdx}`} className="m-0 leading-relaxed text-text-primary break-words [overflow-wrap:anywhere]">
        {renderInlineFormatting(line)}
      </p>
    );
  });

  flushList();

  return <>{elements}</>;
};

function renderInlineFormatting(text: string): React.ReactNode {
  // Regex to split on bold (text), inline code (`code`), and italics (*text*)
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g);

  return tokens.map((token, idx) => {
    if (token.startsWith("**") && token.endsWith("**")) {
      return (
        <strong key={idx} className="font-bold text-text-primary">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <code
          key={idx}
          className="font-mono text-[11px] bg-bg-dark text-accent-cyan border border-border-color px-1.5 py-0.5 rounded mx-0.5 break-all inline-block"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    if (token.startsWith("*") && token.endsWith("*") && token.length > 2) {
      return (
        <em key={idx} className="italic text-text-muted">
          {token.slice(1, -1)}
        </em>
      );
    }
    return token;
  });
}
