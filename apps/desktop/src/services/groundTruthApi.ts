import { fetchWithAuth } from './fetchUtils';

/**
 * Ground-truth capture — an engineer's manual check of a drawing pair.
 *
 * Separate from `auditsApi` on purpose. That module carries *corrections to engine output*:
 * every call there presupposes a finding the engine already produced, so it can only ever
 * describe precision. These calls carry a human reading the drawings with no engine involved,
 * which is the only kind of record that can describe what the engine **missed**.
 *
 * Markings are posted **one at a time, as they are stamped.** A submit-shaped API loses an hour
 * of work to one crash — `M745230A01` carries 68 addressable rows — and an annotator who has
 * lost an hour does not come back. `submitSession` finalises; it is not when the data first
 * exists.
 */

export type MarkingStatus = 'MATCHED' | 'ADDED' | 'REMOVED' | 'CHANGED' | 'NOT_A_FINDING';

/**
 * One clicked entity, as the client saw it.
 *
 * Every key that might survive a re-extraction is sent, because none of them is sufficient
 * alone: `ExtractionPipeline.run` deletes and re-inserts a drawing's entities, so a Mongo
 * entity id is worthless the moment anyone runs `/reextract`; a DXF `handle` survives but is
 * absent on block-exploded children, which on reference sheets is nearly everything. The
 * server stamps `coordinates` into a `CadPoint` with render-bounds provenance — it owns the
 * DrawingDocument and we do not.
 */
export interface EntityAddressPayload {
  drawing_id: string;
  handle?: string | null;
  parent_handle?: string | null;
  entity_type: string;
  layer?: string;
  text?: string;
  coordinates?: [number, number] | null;
}

export interface CreateMarkingPayload {
  status: MarkingStatus;
  category: string;
  category_source?: 'human' | 'zone';
  ref_address?: EntityAddressPayload | null;
  rev_address?: EntityAddressPayload | null;
  ref_text?: string;
  rev_text?: string;
  text_was_edited?: boolean;
  is_bulk?: boolean;
  notes?: string;
}

export interface GroundTruthMarking {
  category_source?: 'human' | 'zone';
  id: string;
  session_id: string;
  side: 'ref' | 'rev' | 'both';
  status: MarkingStatus;
  category: string;
  ref_text: string;
  rev_text: string;
  text_was_edited: boolean;
  is_bulk: boolean;
  notes: string;
  annotator: string;
  ref_handle: string | null;
  rev_handle: string | null;
  ref_coordinates: [number, number] | null;
  rev_coordinates: [number, number] | null;
  created_at: string;
  retracted_at: string | null;
}

export interface ManualCheckSession {
  id: string;
  room_id: string;
  ref_drawing_id: string;
  rev_drawing_id: string;
  annotator: string;
  status: 'in_progress' | 'submitted';
  notes: string;
  marking_count: number;
  started_at: string;
  submitted_at: string | null;
}

async function unwrap<T>(response: Response, what: string): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${what} failed (${response.status}): ${body}`);
  }
  const json = await response.json();
  return json.data as T;
}

const jsonPost = (body: unknown) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function createManualCheckSession(payload: {
  room_id: string;
  ref_drawing_id: string;
  rev_drawing_id: string;
  annotator?: string;
  notes?: string;
}): Promise<ManualCheckSession> {
  const res = await fetchWithAuth('/api/v1/ground-truth/sessions', jsonPost(payload));
  return unwrap<ManualCheckSession>(res, 'Opening a manual check');
}

export async function listManualCheckSessions(roomId?: string): Promise<ManualCheckSession[]> {
  const query = roomId ? `?room_id=${encodeURIComponent(roomId)}` : '';
  const res = await fetchWithAuth(`/api/v1/ground-truth/sessions${query}`, { method: 'GET' });
  return unwrap<ManualCheckSession[]>(res, 'Listing manual checks');
}

export async function listMarkings(sessionId: string): Promise<GroundTruthMarking[]> {
  const res = await fetchWithAuth(
    `/api/v1/ground-truth/sessions/${encodeURIComponent(sessionId)}/markings`,
    { method: 'GET' },
  );
  return unwrap<GroundTruthMarking[]>(res, 'Loading markings');
}

export async function createMarking(
  sessionId: string,
  payload: CreateMarkingPayload,
): Promise<GroundTruthMarking> {
  const res = await fetchWithAuth(
    `/api/v1/ground-truth/sessions/${encodeURIComponent(sessionId)}/markings`,
    jsonPost(payload),
  );
  return unwrap<GroundTruthMarking>(res, 'Recording the marking');
}

export async function updateMarking(
  markingId: string,
  payload: Partial<Pick<CreateMarkingPayload, 'status' | 'category' | 'ref_text' | 'rev_text' | 'is_bulk' | 'notes'>>,
): Promise<GroundTruthMarking> {
  const res = await fetchWithAuth(`/api/v1/ground-truth/markings/${encodeURIComponent(markingId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return unwrap<GroundTruthMarking>(res, 'Updating the marking');
}

/**
 * Take a marking back.
 *
 * The server marks it retracted rather than deleting it: the collection is both the dataset and
 * the record of who asserted what, and a retraction is itself information — a human changed
 * their mind, which a later consumer may weigh differently from a decision never made.
 * Idempotent, so a retry after a dropped response is safe.
 */
export async function retractMarking(markingId: string): Promise<GroundTruthMarking> {
  const res = await fetchWithAuth(`/api/v1/ground-truth/markings/${encodeURIComponent(markingId)}`, {
    method: 'DELETE',
  });
  return unwrap<GroundTruthMarking>(res, 'Retracting the marking');
}

export async function submitSession(sessionId: string): Promise<ManualCheckSession> {
  const res = await fetchWithAuth(
    `/api/v1/ground-truth/sessions/${encodeURIComponent(sessionId)}/submit`,
    jsonPost({}),
  );
  return unwrap<ManualCheckSession>(res, 'Submitting the manual check');
}

export async function reopenSession(sessionId: string): Promise<ManualCheckSession> {
  const res = await fetchWithAuth(
    `/api/v1/ground-truth/sessions/${encodeURIComponent(sessionId)}/reopen`,
    jsonPost({}),
  );
  return unwrap<ManualCheckSession>(res, 'Reopening the manual check');
}

