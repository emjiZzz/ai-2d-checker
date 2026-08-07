/**
 * roomsApi.ts — Network layer for the Rooms domain (SRP: no React, no cache)
 *
 * Exposes typed async functions for every room HTTP operation.
 * All reads accept an AbortSignal from TanStack Query for race protection.
 * Mutations do NOT accept signals — aborting a write mid-flight risks
 * leaving the server in an inconsistent state; rollback handles failures.
 */

import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";
import type { Room } from "../stores/roomStore";

// ─── Mutation parameter types ─────────────────────────────────────────────────

export interface CreateRoomParams {
  name: string;
  description?: string;
  client_name?: string;
  comparison_method?: "rag";
}

export interface UpdateRoomParams {
  roomId: string;
  payload: Partial<Pick<Room, "name" | "description" | "client_name">>;
}

// ─── Rollback context types (consumed by useRooms.ts) ────────────────────────

export interface DeleteRoomContext {
  previousRooms: Room[];
}

export interface UpdateRoomContext {
  previousRooms: Room[];
}

// ─── Public API ───────────────────────────────────────────────────────────────

/** GET /api/v1/rooms — fetches the full rooms list. Signal enables race abort. */
export async function fetchRooms(signal: AbortSignal): Promise<Room[]> {
  const res = await fetch(`${baseUrl()}/api/v1/rooms`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<Room[]>(res);
}

/** GET /api/v1/rooms/:id — fetches a single room's metadata. */
export async function fetchRoom(roomId: string, signal: AbortSignal): Promise<Room> {
  const res = await fetch(`${baseUrl()}/api/v1/rooms/${roomId}`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<Room>(res);
}

/** POST /api/v1/rooms — creates a new room. Returns the server-generated Room. */
export async function createRoom(params: CreateRoomParams): Promise<Room> {
  const res = await fetch(`${baseUrl()}/api/v1/rooms`, {
    method: "POST",
    headers: { ...buildHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({
      name: params.name,
      description: params.description ?? null,
      client_name: params.client_name ?? null,
      comparison_method: params.comparison_method ?? "rag",
    }),
  });
  return parseOrThrow<Room>(res);
}

/** PATCH /api/v1/rooms/:id — updates room fields. */
export async function updateRoom(params: UpdateRoomParams): Promise<Room> {
  const res = await fetch(`${baseUrl()}/api/v1/rooms/${params.roomId}`, {
    method: "PATCH",
    headers: { ...buildHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(params.payload),
  });
  return parseOrThrow<Room>(res);
}

/** DELETE /api/v1/rooms/:id — deletes a room. */
export async function deleteRoom(roomId: string): Promise<{ deleted: boolean }> {
  const res = await fetch(`${baseUrl()}/api/v1/rooms/${roomId}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  return parseOrThrow<{ deleted: boolean }>(res);
}
