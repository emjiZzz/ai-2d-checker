import { z } from "zod";

export const DrawingItemSchema = z.object({
  id: z.string(),
  file_name: z.string(),
  file_path: z.string(),
  format: z.string(),
  file_size_bytes: z.number().optional(),
  entity_counts: z.record(z.string(), z.number()),
  metadata: z.record(z.string(), z.any()),
  status: z.string().optional(),
  created_at: z.string()
});

export const RoomSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  client_name: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  last_opened_at: z.string().nullable(),
  active_old_drawing_id: z.string().nullable().optional(),
  active_new_drawing_id: z.string().nullable().optional(),
  active_old_drawing_name: z.string().nullable().optional(),
  active_new_drawing_name: z.string().nullable().optional(),
  active_audit_session_id: z.string().nullable().optional(),
  physical_comparison_results: z.any().nullable().optional(),
  // Must be declared here or Zod's object parse silently strips it from every room fetch,
  // making the zone gate appear to work on click and then re-close on the next sync.
  zones_confirmed_for: z.string().nullable().optional(),
  // Only the deterministic method survives (ADR-006), renamed from `rag`. Both spellings are
  // accepted and folded to the new one: the backend normalises on input, but a room fetched
  // straight out of a *cached* response — or a backend older than the rename — can still say
  // `"rag"`, and Zod validates what actually arrives rather than what should. `.optional()`
  // because a room created before the field existed does not carry it at all.
  comparison_method: z
    .enum(["deterministic", "rag"])
    .transform(() => "deterministic" as const)
    .default("deterministic")
    .optional(),
  participants: z.array(z.string()).optional()
});

/**
 * Coordinate envelope as persisted by the backend
 * (services/backend/domain/models/cad_point.py). Bare [x, y] pairs are still accepted so
 * a producer that never went through the stamping path does not fail validation.
 */
export const CadPointSchema = z.object({
  x: z.number(),
  y: z.number(),
  space: z.enum(["model", "paper", "render"]).default("render"),
  layout: z.string().nullable().optional(),
  viewport_index: z.number().default(-1),
  transform_version: z.number().default(0),
  bounds: z.array(z.number()).nullable().optional(),
});

export const CoordinateSchema = z.union([
  CadPointSchema,
  z.tuple([z.number(), z.number()]),
]);

export const ViolationSchema = z.object({
  id: z.string(),
  severity: z.enum(["critical", "high", "medium", "low"]),
  category: z.string(),
  description: z.string(),
  recommendation: z.string(),
  affected_entities: z.array(z.string()),
  confidence: z.number(),
  coordinates: CoordinateSchema.optional(),
  ref_coordinates: CoordinateSchema.optional(),
  standard_reference: z.string().optional(),
  pen_type: z.string().optional(),
  // Three-state supervisor verdict. `null`/absent means nobody has reviewed it — which
  // `is_resolved: false` cannot distinguish from an explicit REJECTED.
  resolution_type: z.enum(["APPROVED", "REJECTED"]).nullable().optional(),
  is_resolved: z.boolean().optional(),
  resolved_at: z.string().nullable().optional(),
  original_value: z.string().optional(),
  checker_remarks: z.string().optional(),
});

// A wrapper for lists of entities
export const RoomListSchema = z.array(RoomSchema);
export const DrawingListSchema = z.array(DrawingItemSchema);
