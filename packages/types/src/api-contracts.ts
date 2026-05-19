export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: ApiError | null;
  timestamp: string;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}

export interface SystemHealth {
  status: "healthy" | "unhealthy" | "degraded";
  version: string;
  uptime: number;
  services: {
    mongodb: boolean;
    sidecar: boolean;
    oda_converter: boolean;
  };
}
