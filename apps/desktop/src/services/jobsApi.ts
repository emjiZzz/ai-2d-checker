import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";
import type { Job } from "../stores/drawingStore";

/** GET /api/v1/jobs/:jobId */
export async function fetchJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  const res = await fetch(`${baseUrl()}/api/v1/jobs/${jobId}`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<Job>(res);
}
