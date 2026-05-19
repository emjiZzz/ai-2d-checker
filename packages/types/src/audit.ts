export type AuditStatus = "pending" | "processing" | "completed" | "failed";

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface AuditViolation {
  id: string;
  rule_id: string;
  standard_section: string;
  severity: Severity;
  message: string;
  entity_ids: string[];
  bounding_box?: [number, number, number, number]; // [min_x, min_y, max_x, max_y]
  suggested_fix?: string;
}

export interface AuditResult {
  id: string;
  drawing_id: string;
  standard_id: string;
  status: AuditStatus;
  compliance_score: number;
  violations: AuditViolation[];
  started_at: string;
  completed_at?: string;
  error_message?: string;
  ai_model_used: string;
  ai_prompt_version: string;
}

export interface EngineeringStandard {
  id: string;
  name: string;
  version: string;
  description: string;
  file_path: string;
  rules_count: number;
  uploaded_at: string;
}
