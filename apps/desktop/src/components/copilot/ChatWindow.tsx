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
    <div className="chat-window" style={{ width: '400px' }}>
      <div className="chat-messages-container flex-1 overflow-y-auto p-4 custom-scrollbar" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`chat-bubble ${msg.role === 'user' ? 'user' : 'assistant'}`}>
              <StreamingMessage content={msg.content} isStreaming={msg.isStreaming} citations={msg.citations} />
            </div>
          </div>
        ))}
        {isThinking && (
          <div className="flex justify-start">
            <div className="chat-bubble assistant">
              <span className="animate-pulse text-gray-400 text-sm">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <ChatInput />
    </div>
  );
};
