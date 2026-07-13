import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock Tauri APIs to prevent Node.js crashes
vi.mock('@tauri-apps/api', () => ({
  invoke: vi.fn(() => Promise.resolve()),
}));

vi.mock('@tauri-apps/plugin-dialog', () => ({
  save: vi.fn(() => Promise.resolve('/mock/path/to/file.pdf')),
}));

vi.mock('idb-keyval', () => ({
  get: vi.fn(() => Promise.resolve(null)),
  set: vi.fn(() => Promise.resolve()),
  del: vi.fn(() => Promise.resolve()),
}));

// Mock browser APIs if missing in jsdom
if (typeof window !== 'undefined') {
  // Mock ResizeObserver
  class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserver;
}
