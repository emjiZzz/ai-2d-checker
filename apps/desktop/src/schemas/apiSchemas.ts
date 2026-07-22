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
  comparison_method: z.enum(["rag", "rag_ai", "ai_vision"]).default("rag").optional(),
  participants: z.array(z.string()).optional()
});

export const ViolationSchema = z.object({
  id: z.string(),
  severity: z.enum(["critical", "high", "medium", "low"]),
  category: z.string(),
  description: z.string(),
  recommendation: z.string(),
  affected_entities: z.array(z.string()),
  confidence: z.number(),
  coordinates: z.tuple([z.number(), z.number()]).optional(),
  ref_coordinates: z.tuple([z.number(), z.number()]).optional(),
  standard_reference: z.string().optional(),
  pen_type: z.string().optional(),
  is_resolved: z.boolean().optional(),
  resolved_at: z.string().nullable().optional(),
  original_value: z.string().optional(),
  checker_remarks: z.string().optional(),
});

// A wrapper for lists of entities
export const RoomListSchema = z.array(RoomSchema);
export const DrawingListSchema = z.array(DrawingItemSchema);
