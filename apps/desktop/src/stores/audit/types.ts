export interface StandardDocument {
  id: string;
  name: string;
  file_path: string;
  standard_hash: string;
  file_size_bytes: number;
  format: string;
  category: string | null;
  description: string | null;
  metadata: Record<string, any>;
  created_at: string;
  scope?: string;
  client_name?: string | null;
}

export interface AuditSession {
  id: string;
  drawing_id: string;
  reference_drawing_id?: string | null;
  standard_id?: string | null;
  client_name?: string | null;
  status: string;
  compliance_score: number | null;
  confidence_score: number | null;
  error_message: string | null;
  timings: Record<string, number>;
  diagnostics: Record<string, any>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  remarks?: string | null;
  is_restored?: boolean;
}

export interface AuditViolation {
  id: string;
  audit_session_id: string;
  severity: string;
  category: string;
  description: string;
  recommendation: string;
  affected_entities: Array<Record<string, any>>;
  confidence: number;
  source: string;
  coordinates: number[][] | null;
  standard_reference: string | null;
  pen_type: string;
  /** null = unreviewed. Distinct from REJECTED, which `is_resolved: false` also produces. */
  resolution_type: "APPROVED" | "REJECTED" | null;
  is_resolved: boolean;
  resolved_at: string | null;
  checker_remarks: string | null;
  created_at: string;
}

export interface StandardsSlice {
  standards: StandardDocument[];
  activeStandard: StandardDocument | null;
  uploadStatus: "idle" | "uploading" | "success" | "error";
  uploadProgress: number;

  fetchStandards: () => Promise<void>;
  uploadStandard: (file: File, name: string, category?: string, description?: string, scope?: string, clientName?: string) => Promise<boolean>;
  deleteStandard: (id: string) => Promise<boolean>;
  updateStandard: (id: string, name: string, category: string, description: string) => Promise<boolean>;
}

export interface SessionsSlice {
  sessions: AuditSession[];
  activeSession: AuditSession | null;
  activeViolations: AuditViolation[];
  activeDiagnostics: Record<string, any> | null;
  auditState: "idle" | "processing" | "completed" | "failed";
  errorMessage: string | null;

  fetchSessions: () => Promise<void>;
  launchAudit: (drawingId: string, standardId: string) => Promise<boolean>;
  deleteSession: (id: string) => Promise<boolean>;
  updateSession: (id: string, remarks: string) => Promise<boolean>;
  
  _setActiveSession: (session: AuditSession) => void;
  _setAuditState: (state: SessionsSlice["auditState"], error?: string) => void;

  fetchSessionDetails: (sessionId: string) => Promise<void>;
  fetchViolations: (sessionId: string) => Promise<void>;
  fetchDiagnostics: (sessionId: string) => Promise<void>;
  resetStore: () => void;
}

export type AuditState = StandardsSlice & SessionsSlice;
