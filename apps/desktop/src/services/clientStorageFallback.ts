import { createStore, get, set, del } from 'idb-keyval';

// IndexedDB store for Client PC local storage fallback
const offlineStore = createStore('kmti_draftcheck_offline_db', 'offline_files');
const QUEUE_KEY = '__offline_sync_queue__';

export interface OfflineQueueItem {
  id: string; // drawingId or unique identifier
  drawingId: string;
  subfolder: 'uploads' | 'temp';
  fileName: string;
  timestamp: number;
  sizeBytes: number;
}

const isTauriEnv = (): boolean => {
  return typeof window !== 'undefined' && !!(window as any).__TAURI_INTERNALS__;
};

/**
 * Checks whether the NAS storage share (\\KMTI-NAS\Shared\data\ai_checker\storage)
 * is reachable either directly via Client PC network SMB or via backend health check.
 */
export async function checkNasReachable(backendUrl?: string, customNasPath?: string): Promise<boolean> {
  // 1. If in Tauri desktop client, probe native Windows SMB network path directly
  if (isTauriEnv()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      const direct = await invoke<boolean>('check_nas_reachable', { customPath: customNasPath });
      if (direct) return true;
    } catch (e) {
      console.debug('Tauri check_nas_reachable direct check:', e);
    }
  }

  // 2. Query backend /health endpoint to check server's view of NAS
  if (backendUrl) {
    try {
      const res = await fetch(`${backendUrl}/health`, { method: 'GET' });
      if (res.ok) {
        const data = await res.json();
        if (data.services?.nas_storage === true) {
          return true;
        }
      }
    } catch {
      // Backend probe offline
    }
  }

  return false;
}

/**
 * Saves a file into the Client PC's local storage (%APPDATA%\draftcheck\offline_storage\ + IndexedDB).
 * Server PC 3's disk is never touched.
 */
export async function saveClientFallbackFile(
  drawingId: string,
  subfolder: 'uploads' | 'temp',
  fileName: string,
  data: Uint8Array | ArrayBuffer | Blob
): Promise<void> {
  let arrayBuffer: ArrayBuffer;
  let uint8: Uint8Array;

  if (data instanceof Blob) {
    arrayBuffer = await data.arrayBuffer();
    uint8 = new Uint8Array(arrayBuffer);
  } else if (data instanceof ArrayBuffer) {
    arrayBuffer = data;
    uint8 = new Uint8Array(data);
  } else {
    uint8 = data;
    arrayBuffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
  }

  const storageKey = `${subfolder}__${drawingId}__${fileName}`;

  // 1. Save in IndexedDB (Client PC WebView2 local storage)
  await set(storageKey, arrayBuffer, offlineStore);

  // 2. Save in Client PC native disk storage via Tauri if available
  if (isTauriEnv()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('save_client_local_file', {
        subfolder,
        fileName,
        data: Array.from(uint8),
      });
    } catch (err) {
      console.warn('Failed to save to Client PC native offline dir:', err);
    }
  }

  // 3. Register in local sync queue
  const queue = (await get<OfflineQueueItem[]>(QUEUE_KEY, offlineStore)) || [];
  const existingIdx = queue.findIndex((q) => q.drawingId === drawingId && q.fileName === fileName);
  const item: OfflineQueueItem = {
    id: `${drawingId}_${fileName}`,
    drawingId,
    subfolder,
    fileName,
    timestamp: Date.now(),
    sizeBytes: arrayBuffer.byteLength,
  };

  if (existingIdx >= 0) {
    queue[existingIdx] = item;
  } else {
    queue.push(item);
  }
  await set(QUEUE_KEY, queue, offlineStore);
  console.info(`[Client Storage] Saved offline fallback file '${fileName}' (${item.sizeBytes} bytes) on Client PC.`);
}

/**
 * Retrieves an offline 3D glTF model from Client PC local storage if NAS is offline.
 */
export async function getClientFallbackGltf(drawingId: string): Promise<ArrayBuffer | null> {
  const fileName = `model_${drawingId}.gltf`;
  const storageKey = `temp__${drawingId}__${fileName}`;

  // Check IndexedDB
  const cached = await get<ArrayBuffer>(storageKey, offlineStore);
  if (cached) {
    console.info(`[Client Storage] Loaded 3D glTF model for drawing ${drawingId} from IndexedDB local storage.`);
    return cached;
  }

  // Check Tauri Client PC disk storage
  if (isTauriEnv()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      const bytes = await invoke<number[]>('read_client_local_file', {
        subfolder: 'temp',
        fileName,
      });
      if (bytes && bytes.length > 0) {
        const u8 = new Uint8Array(bytes);
        console.info(`[Client Storage] Loaded 3D glTF model for drawing ${drawingId} from Client PC disk storage.`);
        return u8.buffer;
      }
    } catch {
      // Not on disk
    }
  }

  return null;
}

/**
 * Lists all pending offline files awaiting sync to NAS.
 */
export async function getPendingOfflineQueue(): Promise<OfflineQueueItem[]> {
  return (await get<OfflineQueueItem[]>(QUEUE_KEY, offlineStore)) || [];
}

/**
 * Deletes a file from Client PC local storage after successful sync to NAS.
 */
export async function deleteClientFallbackFile(
  drawingId: string,
  subfolder: 'uploads' | 'temp',
  fileName: string
): Promise<void> {
  const storageKey = `${subfolder}__${drawingId}__${fileName}`;
  await del(storageKey, offlineStore);

  if (isTauriEnv()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('delete_client_local_file', { subfolder, fileName });
    } catch {
      // Ignored
    }
  }

  const queue = (await get<OfflineQueueItem[]>(QUEUE_KEY, offlineStore)) || [];
  const updated = queue.filter((q) => !(q.drawingId === drawingId && q.fileName === fileName));
  await set(QUEUE_KEY, updated, offlineStore);
  console.info(`[Client Storage] Cleaned up synced file '${fileName}' from Client PC local storage.`);
}

/**
 * Auto-sync engine: When the NAS becomes reachable, iterates over all pending files
 * stored on the Client PC, writes them directly to \\KMTI-NAS\Shared\data\ai_checker\storage,
 * verifies the transfer, and deletes the local copies from the Client PC.
 */
export async function syncPendingFilesToNas(
  backendUrl?: string,
  apiToken?: string,
  customNasPath?: string
): Promise<{ synced: number; failed: number }> {
  const isOnline = await checkNasReachable(backendUrl, customNasPath);
  if (!isOnline) {
    return { synced: 0, failed: 0 };
  }

  const queue = await getPendingOfflineQueue();
  if (!queue || queue.length === 0) {
    return { synced: 0, failed: 0 };
  }

  console.info(`[Client Storage] NAS reachable! Initiating sync for ${queue.length} pending offline files...`);
  let synced = 0;
  let failed = 0;

  for (const item of queue) {
    try {
      let data: ArrayBuffer | null = null;
      const storageKey = `${item.subfolder}__${item.drawingId}__${item.fileName}`;
      data = (await get<ArrayBuffer>(storageKey, offlineStore)) || null;

      if (!data && isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core');
        const bytes = await invoke<number[]>('read_client_local_file', {
          subfolder: item.subfolder,
          fileName: item.fileName,
        });
        if (bytes) {
          data = new Uint8Array(bytes).buffer;
        }
      }

      if (!data) {
        // Data lost or already cleaned up
        await deleteClientFallbackFile(item.drawingId, item.subfolder, item.fileName);
        continue;
      }

      let syncSuccess = false;

      // Primary strategy: If in Tauri, write directly to NAS over Windows SMB share
      if (isTauriEnv()) {
        try {
          const { invoke } = await import('@tauri-apps/api/core');
          const u8 = new Uint8Array(data);
          syncSuccess = await invoke<boolean>('sync_file_to_nas', {
            subfolder: item.subfolder,
            fileName: item.fileName,
            data: Array.from(u8),
            customPath: customNasPath,
          });
        } catch (e) {
          console.warn(`[Client Storage] Direct NAS write failed for ${item.fileName}:`, e);
        }
      }

      // Secondary strategy: Upload via backend /drawings/sync-file
      if (!syncSuccess && backendUrl) {
        const formData = new FormData();
        const blob = new Blob([data]);
        formData.append('file', blob, item.fileName);
        formData.append('subfolder', item.subfolder);
        formData.append('target_name', item.fileName);

        const headers: Record<string, string> = {};
        if (apiToken) headers['Authorization'] = `Bearer ${apiToken}`;

        const res = await fetch(`${backendUrl}/api/v1/drawings/sync-file`, {
          method: 'POST',
          headers,
          body: formData,
        });

        if (res.ok) {
          syncSuccess = true;
        }
      }

      if (syncSuccess) {
        // Verified! Delete from Client PC local storage to free disk space
        await deleteClientFallbackFile(item.drawingId, item.subfolder, item.fileName);
        synced++;
      } else {
        failed++;
      }
    } catch (err) {
      console.error(`[Client Storage] Error syncing ${item.fileName} to NAS:`, err);
      failed++;
    }
  }

  console.info(`[Client Storage] Sync complete. Synced: ${synced}, Failed: ${failed}.`);
  return { synced, failed };
}

// Start background auto-sync runner (every 20 seconds)
let syncIntervalId: any = null;

export function startBackgroundNasSync(backendUrl?: string, apiToken?: string) {
  if (syncIntervalId) return;
  syncIntervalId = setInterval(() => {
    void syncPendingFilesToNas(backendUrl, apiToken);
  }, 20_000);
}

export function stopBackgroundNasSync() {
  if (syncIntervalId) {
    clearInterval(syncIntervalId);
    syncIntervalId = null;
  }
}
