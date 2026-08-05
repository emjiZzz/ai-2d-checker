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
