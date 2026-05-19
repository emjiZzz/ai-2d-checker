import React, { useState } from 'react';
import { useCopilotStore } from '../../stores/copilotStore';

export const ChatInput: React.FC = () => {
  const [input, setInput] = useState('');
  const { addMessage, setThinking } = useCopilotStore();

  const handleSend = () => {
    if (!input.trim()) return;
    
    // Add user message optimistically
    addMessage({
      id: Date.now().toString(),
      role: 'user',
      content: input,
      isStreaming: false,
      citations: []
    });
    
    setInput('');
    setThinking(true);
    
    // In production, this opens an SSE EventSource connection to the backend
    setTimeout(() => setThinking(false), 1000);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="p-4 bg-gray-900 border-t border-gray-800">
      <div className="relative">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Copilot about geometry or standards..."
          className="w-full bg-gray-800 border border-gray-700 rounded-lg py-2 pl-3 pr-10 text-sm text-white focus:border-blue-500 outline-none resize-none"
          rows={2}
        />
        <button 
          onClick={handleSend}
          className="absolute right-2 bottom-2 p-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-md transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </button>
      </div>
      <div className="text-[10px] text-gray-500 mt-2 text-center">
        AI responses are grounded in verified engineering standards via RAG.
      </div>
    </div>
  );
};
