import { fetchWithAuth } from './fetchUtils';

/** Fixed-shape feature snapshot of a finding at correction time (mirrors backend
 *  api.schemas.FindingSnapshot). text_similarity/match_distance/is_numericish may be left
 *  null — the backend recomputes them from the texts/coords with the same normalization the
 *  runtime differ uses, so the frontend doesn't have to. */
export interface FindingSnapshotPayload {
  ref_text?: string | null;
  rev_text?: string | null;
  det_status?: string | null;
  category?: string | null;
  feature?: string | null;
  text_similarity?: number | null;
  match_distance?: number | null;
  ref_coord?: number[] | null;
  rev_coord?: number[] | null;
  is_numericish?: boolean | null;
}

// Mirrors services/backend/api/schemas.py::HumanCorrectedStatus. The two `mispaired_*` verbs
// say the engine matched the wrong entities (or missed a match) rather than that its verdict
// was wrong — a statement none of the others can make. See trainer.MATCHER_FEEDBACK.
export type HumanCorrectedStatus =
  | 'dismissed'
  | 'confirmed_valid'
  | 'category_override'
  | 'verdict_matched'
  | 'verdict_changed'
  | 'confirmed_change'
  | 'value_correction'
  | 'mispaired_missing_counterpart'
  | 'mispaired_wrong_match';

export interface AuditFeedbackPayload {
  session_id: string;
  drawing_id: string;
  client_name?: string | null;
  entity_text: string;
  entity_handle?: string | null;
  category: string;
  original_status: string;
  human_corrected_status: HumanCorrectedStatus;
  human_comment?: string | null;
  coordinates?: number[] | null;
  corrected_category?: string | null;
  corrected_value?: string | null;
  finding_snapshot?: FindingSnapshotPayload | null;
}

export interface AuditFeedbackResponse {
  id: string;
  status: string;
  auto_documented: boolean;
  message: string;
}

/** Status of the learned-correction model (GET /audits/learning/status). */
export interface LearnedModelStatus {
  trained_at: string | null;
  n_total: number;
  n_verdict: number;
  n_category: number;
  n_exact_overrides: number;
  min_train: number;
  verdict_ready: boolean;
  category_ready: boolean;
  metrics: Record<string, any>;
  generated_at?: string;
}

export async function submitAuditFeedbackPayload(
  payload: AuditFeedbackPayload
): Promise<AuditFeedbackResponse> {
  const response = await fetchWithAuth('/api/v1/audits/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to submit audit feedback (${response.status}): ${errorText}`);
  }

  const json = await response.json();
  return json.data;
}

/** Take back a correction submitted by mistake, so it no longer trains the model.
 *
 * The backend marks it retracted rather than deleting it — the collection is the audit trail
 * of who taught the model what — and retrains without it. Idempotent, so a retry after a
 * dropped response is safe.
 */
export async function retractAuditFeedback(feedbackId: string): Promise<void> {
  const response = await fetchWithAuth(
    `/api/v1/audits/feedback/${encodeURIComponent(feedbackId)}/retract`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' } }
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to retract audit feedback (${response.status}): ${errorText}`);
  }
}

/** The three states a finding can be in. `null` is "no supervisor has looked at this yet" and is
 *  NOT the same as REJECTED — `is_resolved` alone cannot tell them apart, which is why the
 *  backend response carries `resolution_type` separately. Mirrors
 *  domain.models.audit_violation.RESOLUTION_APPROVED / RESOLUTION_REJECTED. */
export type ViolationResolution = 'APPROVED' | 'REJECTED' | null;

export interface ViolationReviewResult {
  id: string;
  resolution_type: ViolationResolution;
  is_resolved: boolean;
  checker_remarks: string | null;
  resolved_at: string | null;
}

/** PATCH /api/v1/audits/violations/{id}/review — record a supervisor verdict on a finding.
 *
 * This is the write that fills the `lessons` retrieval collection: the backend re-derives the
 * index from confirmed violations after each review. Until this endpoint had a caller, all 1,322
 * violations in the database were unreviewed and `lessons` was permanently empty — the index was
 * being queried by a read path that no writer could ever populate.
 *
 * `isValid: false` (REJECTED) is a real signal, not a no-op: it records that the engine raised
 * something a human judged wrong. It deliberately does NOT feed the lessons index — a false
 * positive fed back as a lesson teaches the opposite of the intended thing.
 */
export async function reviewViolation(
  violationId: string,
  isValid: boolean,
  remarks = ''
): Promise<ViolationReviewResult> {
  const response = await fetchWithAuth(
    `/api/v1/audits/violations/${encodeURIComponent(violationId)}/review`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_valid: isValid, remarks }),
    }
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to record violation review (${response.status}): ${errorText}`);
  }
  const json = await response.json();
  return json.data;
}

/** ADR-010. `ok` is the only status carrying a generated summary; every other value means the
 *  client should render `fallback_text`, which is always populated and always true. */
export type SummaryStatus = 'ok' | 'withheld' | 'unavailable' | 'disabled' | 'not_applicable';

export interface SummaryClaim {
  text: string;
  finding_ids: string[];
}

export interface ComparisonSummary {
  status: SummaryStatus;
  headline: string | null;
  claims: SummaryClaim[];
  /** Deterministic template. Present on every path, including `ok`. */
  fallback_text: string;
  withheld_reasons: string[];
  withheld_detail: string;
  finding_count: number;
  model_used: string | null;
  cached: boolean;
}

/** GET /api/v1/audits/sessions/{id}/summary — grounded summary of a session's findings.
 *
 * Never throws because a summary could not be produced: "no summary" is normal operation and
 * arrives as a `status`, not an error. It throws only on transport/HTTP failure.
 */
export async function getComparisonSummary(sessionId: string): Promise<ComparisonSummary> {
  const response = await fetchWithAuth(
    `/api/v1/audits/sessions/${encodeURIComponent(sessionId)}/summary`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch comparison summary (${response.status}): ${errorText}`);
  }
  const json = await response.json();
  return json.data;
}

/** GET /api/v1/audits/learning/status — learned-correction model readiness + metrics. */
export async function getLearnedModelStatus(): Promise<LearnedModelStatus> {
  const response = await fetchWithAuth('/api/v1/audits/learning/status');
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch learned-model status (${response.status}): ${errorText}`);
  }
  const json = await response.json();
  return json.data;
}

/** POST /api/v1/audits/learning/retrain — force an immediate retrain from feedback. */
export async function retrainLearnedModel(): Promise<LearnedModelStatus> {
  const response = await fetchWithAuth('/api/v1/audits/learning/retrain', { method: 'POST' });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to retrain learned model (${response.status}): ${errorText}`);
  }
  const json = await response.json();
  return json.data;
}
