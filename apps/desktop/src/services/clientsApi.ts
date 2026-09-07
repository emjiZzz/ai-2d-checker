import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";
import type { ClientItem } from "../stores/workspaceStore";

export async function fetchClients(signal?: AbortSignal): Promise<ClientItem[]> {
  const res = await fetch(`${baseUrl()}/api/v1/clients`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<ClientItem[]>(res);
}

export async function createClient(name: string): Promise<void> {
  const res = await fetch(`${baseUrl()}/api/v1/clients`, {
    method: "POST",
    headers: { ...buildHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await parseOrThrow<unknown>(res);
}

export async function deleteClient(name: string): Promise<void> {
  const res = await fetch(`${baseUrl()}/api/v1/clients/${name}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  await parseOrThrow<unknown>(res);
}
