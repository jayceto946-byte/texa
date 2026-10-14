import { apiFetch } from '../../api/client';

export type ConversationView = 'active' | 'archived' | 'trashed';
export type ConversationAction = 'pin' | 'unpin' | 'archive' | 'restore' | 'trash';
export type ConversationManagement = {
  state: ConversationView;
  pinned: boolean;
  revision: number;
  updated_at?: string;
  previous_state?: ConversationView | null;
};
export type ConversationSummary = {
  id: string;
  title: string;
  subject: string;
  book_name: string;
  updated_at: string;
  message_count: number;
  management: ConversationManagement;
};
export type ConversationListPage = {
  items: ConversationSummary[];
  next_cursor: string | null;
  has_more: boolean;
};
export type BlockingConversationTask = {
  id: string;
  status: string;
  run_id: string;
  revision?: number;
  can_cancel?: boolean;
};

export class ConversationError extends Error {
  code: string;
  tasks: BlockingConversationTask[];
  constructor(code: string, message: string, tasks: BlockingConversationTask[] = []) {
    super(message); this.code = code; this.tasks = tasks;
  }
}

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await apiFetch(`/chat/conversations${path}`, {
    method: body === undefined ? 'GET' : 'POST', signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok || !payload.success) throw new ConversationError(payload.code || 'request_failed', payload.message || '会话操作失败', payload.tasks || []);
  return payload.data as T;
}

export const conversationApi = {
  list: (query: string, signal?: AbortSignal) => request<ConversationListPage>(`?${query}`, undefined, signal),
  management: (id: string, signal?: AbortSignal) => request<ConversationManagement>(`/${encodeURIComponent(id)}/management`, undefined, signal),
  change: (id: string, action: ConversationAction, revision: number, operationId: string) => request<ConversationManagement>(`/${encodeURIComponent(id)}/management`, { action, expected_revision: revision, operation_id: operationId }),
};

export function notifyConversationChange(id: string, management: ConversationManagement) {
  window.dispatchEvent(new CustomEvent('conversations:changed', { detail: { id, management } }));
}
