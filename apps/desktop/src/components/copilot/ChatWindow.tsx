import React, { useRef, useEffect } from 'react';
import { useCopilotStore } from '../../stores/copilotStore';
import { StreamingMessage } from './StreamingMessage';
import { ChatInput } from './ChatInput';

export const ChatWindow: React.FC = () => {
  const { messages, isThinking } = useCopilotStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom during streaming
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  return (
    <div className="flex flex-col h-full bg-bg-dark border-l border-border-color w-[400px]">
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl p-3.5 text-xs leading-relaxed mb-2 ${msg.role === 'user' ? 'bg-[var(--bg-bubble-user)] text-text-primary rounded-br-xs self-end' : 'bg-bg-card text-text-primary border border-border-color rounded-bl-xs self-start'}`}>
              <StreamingMessage content={msg.content} isStreaming={msg.isStreaming} citations={msg.citations} />
            </div>
          </div>
        ))}
        {isThinking && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl p-3.5 text-xs leading-relaxed mb-2 bg-bg-card text-text-primary border border-border-color rounded-bl-xs self-start">
              <span className="animate-pulse text-zinc-400 text-xs">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <ChatInput />
    </div>
  );
};
