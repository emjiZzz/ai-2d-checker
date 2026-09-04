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

  /**
   * Mock IntersectionObserver.
   *
   * jsdom does not implement it, and a component that constructs one throws during its mount
   * effect — which surfaces as the whole render failing, not as a lazy-loading problem. That is
   * how `RoomsView.test.tsx` came to fail on two assertions about a dialog: `RoomsView` gained a
   * lazy-loading sentinel, and neither test mentions scrolling.
   *
   * **This never fires its callback.** Anything it observes stays permanently un-intersected,
   * so a list paginated by a sentinel shows only its first page under test. That is fine for
   * asserting on what is rendered initially and useless for asserting that more loads — a test
   * of lazy loading has to drive the callback itself rather than trust this stub.
   */
  class IntersectionObserver {
    readonly root: Element | Document | null = null;
    readonly rootMargin: string = '';
    readonly thresholds: ReadonlyArray<number> = [];
    constructor(_callback: IntersectionObserverCallback, _options?: IntersectionObserverInit) {}
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }
  window.IntersectionObserver = IntersectionObserver;
}
