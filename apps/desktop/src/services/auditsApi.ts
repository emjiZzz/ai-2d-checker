import { fetchWithAuth } from './fetchUtils';

export interface AuditFeedbackPayload {
  session_id: string;
  drawing_id: string;
  client_name?: string | null;
  entity_text: string;
  entity_handle?: string | null;
  category: string;
  original_status: string;
  human_corrected_status: 'dismissed' | 'confirmed_valid' | 'category_override';
  human_comment?: string | null;
  coordinates?: number[] | null;
}

export interface AuditFeedbackResponse {
  id: string;
  status: string;
  auto_documented: boolean;
  message: string;
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
