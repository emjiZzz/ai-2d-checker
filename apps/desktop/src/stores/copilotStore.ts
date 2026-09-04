import { create } from 'zustand';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming: boolean;
  citations: string[];
}

interface CopilotState {
  sessionId: string | null;
  messages: Message[];
  isThinking: boolean;
  
  addMessage: (msg: Message) => void;
  updateStreamingMessage: (id: string, chunk: string, isStreaming?: boolean) => void;
  setThinking: (status: boolean) => void;
  clearSession: () => void;
}

export const useCopilotStore = create<CopilotState>((set) => ({
  sessionId: null,
  messages: [],
  isThinking: false,

  addMessage: (msg) => set((state) => ({ 
    messages: [...state.messages, msg] 
  })),
  
  updateStreamingMessage: (id, chunk, isStreaming = true) => set((state) => ({
    messages: state.messages.map(m => 
      m.id === id ? { ...m, content: m.content + chunk, isStreaming } : m
    )
  })),
  
  setThinking: (status) => set({ isThinking: status }),
  
  clearSession: () => set({ messages: [], sessionId: null })
}));
