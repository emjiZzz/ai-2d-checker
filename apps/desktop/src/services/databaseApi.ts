import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";

export interface StorageStats {
  data_size_mb: number;
  storage_size_mb: number;
  objects_count: number;
  limit_mb: number | null;
  usage_percent: number | null;
  is_free_tier: boolean;
  tier_name: string;
  is_warning: boolean;
}

export interface SyncStatus {
  cloud_configured: boolean;
  auto_sync_enabled: boolean;
  sync_interval_seconds: number;
  is_worker_running: boolean;
  last_sync_time: number | null;
  last_sync_status: string;
  last_sync_metrics: Record<string, any>;
}

export interface DatabaseStatusResponse {
  connected: boolean;
  mode: "cloud_primary" | "local_fallback" | "disconnected";
  is_fallback: boolean;
  active_uri: string | null;
  health: {
    status: string;
    latency_ms: number;
    connected: boolean;
    database_name?: string;
  };
  storage: StorageStats;
  sync: SyncStatus;
  timestamp: number;
}

export async function fetchDatabaseStatus(): Promise<DatabaseStatusResponse> {
  const url = `${baseUrl()}/api/v1/database/status`;
  const res = await fetch(url, {
    method: "GET",
    headers: buildHeaders(),
  });
  return parseOrThrow(res);
}

export async function triggerDatabaseSync(): Promise<any> {
  const url = `${baseUrl()}/api/v1/database/sync`;
  const res = await fetch(url, {
    method: "POST",
    headers: buildHeaders(),
  });
  return parseOrThrow(res);
}
