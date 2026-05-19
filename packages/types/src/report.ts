export type ReportFormat = "pdf" | "xlsx" | "json";

export interface Report {
  id: string;
  audit_id?: string;
  comparison_id?: string;
  filename: string;
  format: ReportFormat;
  file_path: string;
  generated_at: string;
  size_bytes: number;
  signee?: string;
  is_finalized: boolean;
}

export interface ReportGenerationRequest {
  audit_id?: string;
  comparison_id?: string;
  format: ReportFormat;
  template_name?: string;
  include_visual_overlays: boolean;
}
