import { apiFetch } from '../../api/client';
import type { Note, NoteDraft, Preflight, Selection, SourceDetail } from './types';
export class NoteApiError extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) { super(message); this.code = code; this.status = status; }
}
export async function noteRequest<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
    const response = await apiFetch(`/notes${path}`, { method, signal, headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const value = await response.json();
    if (!response.ok || !value.success)
        throw new NoteApiError(value.code || 'request_failed', value.message || '笔记请求失败', response.status);
    return value.data as T;
}
export const notesApi = {
    preflight: (selection: Selection, hint = 'auto', completedOnly = false) => noteRequest<Preflight>('/preflight', 'POST', { selection, structure_hint: hint, completed_only: completedOnly }),
    generate: (body: unknown) => noteRequest<{
        draft_id: string;
        job_id: string;
        snapshot_id: string;
    }>('/generations', 'POST', body),
    draft: (id: string, signal?: AbortSignal) => noteRequest<NoteDraft>(`/drafts/${id}`, 'GET', undefined, signal),
    createDraft: (body: unknown) => noteRequest<NoteDraft>('/drafts', 'POST', body),
    patchDraft: (id: string, revision: number, content: unknown) => noteRequest<NoteDraft>(`/drafts/${id}`, 'PATCH', { expected_draft_revision: revision, content }),
    save: (id: string, body: unknown) => noteRequest<{
        note_id: string;
        revision: number;
    }>(`/drafts/${id}/save`, 'POST', body),
    note: (id: string, revision?: string) => noteRequest<Note>(`/${id}${revision ? `/revisions/${revision}` : ''}`),
    source: (id: string, sourceId: string, draft = false, revision?: string) => noteRequest<SourceDetail>(`${draft ? '/drafts' : ''}/${id}/sources/${sourceId}${revision ? `?revision=${revision}` : ''}`),
};
