import React from 'react';

interface StreamingMessageProps {
  content: string;
  isStreaming: boolean;
  citations?: string[];
}

export const StreamingMessage: React.FC<StreamingMessageProps> = ({ content, isStreaming, citations = [] }) => {
  return (
    <div className="streaming-message">
      {/* Markdown rendering goes here (react-markdown) */}
      <span className="whitespace-pre-wrap">{content}</span>
      
      {isStreaming && (
        <span className="inline-block w-2 h-4 bg-gray-400 ml-1 animate-pulse align-middle" />
      )}

      {citations.length > 0 && !isStreaming && (
        <div className="mt-2 pt-2 border-t border-gray-700/50 flex flex-wrap gap-1">
          {citations.map((cite, i) => (
            <span key={i} className="text-[10px] bg-indigo-900/40 text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-800 cursor-help" title="View Standards Reference">
              [{i + 1}] {cite}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
