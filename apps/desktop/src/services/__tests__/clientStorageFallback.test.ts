import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  saveClientFallbackFile,
  getClientFallbackGltf,
  getPendingOfflineQueue,
  deleteClientFallbackFile,
  syncPendingFilesToNas,
  checkNasReachable,
} from '../clientStorageFallback';

// Mock idb-keyval in-memory store
const memoryStore = new Map<string, any>();

vi.mock('idb-keyval', () => ({
  createStore: vi.fn(() => 'mock-store'),
  get: vi.fn(async (key: string) => memoryStore.get(key)),
  set: vi.fn(async (key: string, val: any) => {
    memoryStore.set(key, val);
  }),
  del: vi.fn(async (key: string) => {
    memoryStore.delete(key);
  }),
}));

describe('clientStorageFallback', () => {
  beforeEach(() => {
    memoryStore.clear();
    vi.restoreAllMocks();
  });

  it('saves offline drawing and registers it in the pending queue', async () => {
    const drawingId = 'draw_123';
    const mockBytes = new Uint8Array([1, 2, 3, 4, 5]);

    await saveClientFallbackFile(drawingId, 'temp', `model_${drawingId}.gltf`, mockBytes);

    const queue = await getPendingOfflineQueue();
    expect(queue.length).toBe(1);
    expect(queue[0].drawingId).toBe(drawingId);
    expect(queue[0].fileName).toBe(`model_${drawingId}.gltf`);
    expect(queue[0].subfolder).toBe('temp');
    expect(queue[0].sizeBytes).toBe(5);
  });

  it('retrieves cached 3D glTF model from Client PC local storage', async () => {
    const drawingId = 'draw_456';
    const buffer = new Uint8Array([10, 20, 30]).buffer;

    await saveClientFallbackFile(drawingId, 'temp', `model_${drawingId}.gltf`, buffer);

    const loaded = await getClientFallbackGltf(drawingId);
    expect(loaded).not.toBeNull();
    expect(new Uint8Array(loaded!)).toEqual(new Uint8Array([10, 20, 30]));
  });

  it('deletes fallback file and cleans queue on successful sync', async () => {
    const drawingId = 'draw_789';
    const mockBytes = new Uint8Array([99]);

    await saveClientFallbackFile(drawingId, 'uploads', 'test.dxf', mockBytes);
    expect((await getPendingOfflineQueue()).length).toBe(1);

    await deleteClientFallbackFile(drawingId, 'uploads', 'test.dxf');
    expect((await getPendingOfflineQueue()).length).toBe(0);
  });

  it('syncs pending offline files to NAS via sync endpoint and deletes local copy', async () => {
    const drawingId = 'draw_sync';
    const mockBytes = new Uint8Array([7, 8, 9]);

    await saveClientFallbackFile(drawingId, 'temp', `model_${drawingId}.gltf`, mockBytes);

    // Mock fetch for /health and /drawings/sync-file
    global.fetch = vi.fn(async (url: any) => {
      const urlStr = String(url);
      if (urlStr.includes('/health')) {
        return {
          ok: true,
          json: async () => ({ services: { nas_storage: true } }),
        } as any;
      }
      if (urlStr.includes('/drawings/sync-file')) {
        return {
          ok: true,
          json: async () => ({ success: true, bytes: 3 }),
        } as any;
      }
      return { ok: false } as any;
    });

    const result = await syncPendingFilesToNas('http://192.168.200.149:8080', 'test-token');
    expect(result.synced).toBe(1);
    expect(result.failed).toBe(0);

    // Queue must now be empty and local copy deleted!
    const remainingQueue = await getPendingOfflineQueue();
    expect(remainingQueue.length).toBe(0);
  });

  it('checks NAS reachable via backend probe', async () => {
    global.fetch = vi.fn(async (url: any) => {
      if (String(url).includes('/health')) {
        return {
          ok: true,
          json: async () => ({ services: { nas_storage: true } }),
        } as any;
      }
      return { ok: false } as any;
    });

    const reachable = await checkNasReachable('http://192.168.200.149:8080');
    expect(reachable).toBe(true);
  });
});
