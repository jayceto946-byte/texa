import type { AgentToolResult, AgentToolSpec, ReadOnlyAgentResponse, AnswerMode, AssistantSource, ConceptCandidate, SubjectRouteSuggestion } from '../types';

const DEFAULT_TIMEOUT_MS = 20000;
export const AGENT_REQUEST_TIMEOUT_MS = 55000;
export const AGENT_FALLBACK_TIMEOUT_MS = 60000;
const NON_STREAMING_CHAT_TIMEOUT_MS = 130000;
const API_TOKEN_KEY = 'kaoyan_api_token';
const DESKTOP_API_BASE_KEY = 'kaoyan_desktop_api_base';

function bootstrapDesktopLaunch(): string {
  if (typeof window === 'undefined') return '';
  const hash = window.location.hash.replace(/^#/, '');
  const params = new URLSearchParams(hash);
  const token = (params.get('access_token') || params.get('capture_token'))?.trim();
  const apiBase = params.get('api_base')?.trim() || '';
  if (token) window.localStorage.setItem(API_TOKEN_KEY, token);
  if (apiBase) window.sessionStorage.setItem(DESKTOP_API_BASE_KEY, apiBase);
  if (token || apiBase) {
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  }
  return apiBase || window.sessionStorage.getItem(DESKTOP_API_BASE_KEY)?.trim() || '';
}

const API_BASE = normalizeApiBase(bootstrapDesktopLaunch() || import.meta.env.VITE_API_BASE_URL || '/api');

function authHeaders(initial?: HeadersInit): Headers {
  const headers = new Headers(initial);
  if (typeof window !== 'undefined') {
    const token = window.localStorage.getItem(API_TOKEN_KEY)?.trim();
    if (token) headers.set('X-Kaoyan-Token', token);
  }
  return headers;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.clone().json().catch(() => null);
  const message = payload?.message || payload?.detail || `${fallback}: ${response.status}`;
  return new Error(message);
}

function normalizeApiBase(value: string): string {
  const trimmed = (value || '/api').trim().replace(/\/+$/, '');
  return trimmed || '/api';
}

function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

function authenticatedResourceUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return '';
  try {
    const parsed = new URL(trimmed, window.location.origin);
    if (parsed.pathname === '/api' || parsed.pathname.startsWith('/api/')) {
      return `${API_BASE}${parsed.pathname.slice(4)}${parsed.search}`;
    }
    if (/^https?:\/\//i.test(trimmed)) {
      throw new Error('拒绝从本地 API 之外的地址加载鉴权资源');
    }
  } catch {
    // Fall through to the API-relative form below.
  }
  return apiUrl(trimmed);
}

export type ChatEvent = {
  stage: string;
  request_id?: string;
  elapsed_ms?: number;
  chunk?: string;
  replace?: boolean;
  done?: boolean;
  intent?: string;
  chapters?: string[];
  fast_path?: boolean;
  planner_trace?: Record<string, unknown>;
  content_count?: number;
  message?: string;
  conversation_id?: string;
  turn_id?: string;
  resolution_action?: 'continue' | 'clarify';
  subject_suggestion?: SubjectRouteSuggestion;
  rewritten_question?: string;
  use_textbook_context?: boolean;
  scope_reason?: string;
  answer_mode?: AnswerMode;
  suggested_answer_mode?: AnswerMode;
  retrieval_status?: string;
  retrieval_error?: string;
  state?: { linked_concepts?: ConceptCandidate[]; evidence_sources?: AssistantSource[]; suggested_answer_mode?: AnswerMode };
};

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  const sourceSignal = init.signal;
  const abortFromSource = () => ctrl.abort();
  if (sourceSignal?.aborted) ctrl.abort();
  else sourceSignal?.addEventListener('abort', abortFromSource, { once: true });
  try {
    return await fetch(input, { ...init, headers: authHeaders(init.headers), signal: ctrl.signal });
  } finally {
    window.clearTimeout(timer);
    sourceSignal?.removeEventListener('abort', abortFromSource);
  }
}

export async function apiFetch(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Response> {
  return fetchWithTimeout(apiUrl(path), init, timeoutMs);
}

export async function getAuthenticatedBlob(path: string, signal?: AbortSignal, timeoutMs = 60000): Promise<Blob> {
  const res = await fetchWithTimeout(authenticatedResourceUrl(path), { signal }, timeoutMs);
  if (!res.ok) throw await responseError(res, `GET ${path} failed`);
  return res.blob();
}

export async function getAuthenticatedText(path: string, signal?: AbortSignal, timeoutMs = 60000): Promise<string> {
  const res = await fetchWithTimeout(authenticatedResourceUrl(path), { signal }, timeoutMs);
  if (!res.ok) throw await responseError(res, `GET ${path} failed`);
  return res.text();
}

export async function get(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<any> {
  const res = await fetchWithTimeout(apiUrl(path), {}, timeoutMs);
  if (!res.ok) throw await responseError(res, `GET ${path} failed`);
  return res.json();
}

export async function post(path: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<any> {
  const res = await fetchWithTimeout(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, timeoutMs);
  if (!res.ok) throw await responseError(res, `POST ${path} failed`);
  return res.json();
}

export async function patch(path: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<any> {
  const res = await fetchWithTimeout(apiUrl(path), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, timeoutMs);
  if (!res.ok) throw await responseError(res, `PATCH ${path} failed`);
  return res.json();
}

export async function del(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<any> {
  const res = await fetchWithTimeout(apiUrl(path), { method: 'DELETE' }, timeoutMs);
  if (!res.ok) throw await responseError(res, `DELETE ${path} failed`);
  return res.json();
}

function warnMalformedSse(payload: string, err: unknown) {
  if (import.meta.env.DEV) {
    console.warn('Malformed SSE data:', payload, err);
  } else {
    console.warn('Malformed SSE data');
  }
}

export function consumeSseLine(line: string, onEvent: (event: ChatEvent) => void): boolean {
  const trimmed = line.trim();
  if (!trimmed.startsWith('data: ')) return false;

  const payload = trimmed.slice(6);
  if (payload === '[DONE]') return true;

  try {
    const event = JSON.parse(payload) as ChatEvent;
    onEvent(event);
    return event.stage === 'done' || event.stage === 'error';
  } catch (err) {
    warnMalformedSse(payload, err);
    return false;
  }
}

export function consumeSseChunk(
  chunk: string,
  buffer: string,
  onEvent: (event: ChatEvent) => void,
): { buffer: string; sawTerminalEvent: boolean } {
  const lines = `${buffer}${chunk}`.split('\n');
  const nextBuffer = lines.pop() || '';
  let sawTerminalEvent = false;
  for (const line of lines) {
    sawTerminalEvent = consumeSseLine(line, onEvent) || sawTerminalEvent;
  }
  return { buffer: nextBuffer, sawTerminalEvent };
}

export function flushSseBuffer(buffer: string, onEvent: (event: ChatEvent) => void): boolean {
  if (!buffer.trim()) return false;
  let sawTerminalEvent = false;
  for (const line of buffer.split('\n')) {
    sawTerminalEvent = consumeSseLine(line, onEvent) || sawTerminalEvent;
  }
  return sawTerminalEvent;
}

export function chatStream(
  question: string,
  bookName: string = '',
  subject: string = '',
  conversationId: string = '',
  turnId: string,
  onEvent: (event: ChatEvent) => void,
  onError?: (err: Error) => void,
  answerMode: AnswerMode = 'auto',
): () => void {
  const ctrl = new AbortController();

  (async () => {
    try {
      const res = await fetch(apiUrl('/chat/stream'), {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ question, book_name: bookName, subject, conversation_id: conversationId, turn_id: turnId, answer_mode: answerMode }),
        signal: ctrl.signal,
      });

      if (!res.ok || !res.body) throw await responseError(res, 'SSE failed');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let sawTerminalEvent = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const parsed = consumeSseChunk(decoder.decode(value, { stream: true }), buffer, onEvent);
        buffer = parsed.buffer;
        sawTerminalEvent = parsed.sawTerminalEvent || sawTerminalEvent;
      }

      buffer += decoder.decode();
      sawTerminalEvent = flushSseBuffer(buffer, onEvent) || sawTerminalEvent;

      if (!sawTerminalEvent && !ctrl.signal.aborted) {
        throw new Error('stream ended without terminal event');
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (err instanceof Error && err.name === 'AbortError') return;
      if (onError && err instanceof Error) onError(err);
    }
  })();

  return () => ctrl.abort();
}

export async function chatAsk(
  question: string,
  bookName: string = '',
  subject: string = '',
  conversationId: string = '',
  turnId: string,
  signal?: AbortSignal,
  answerMode: AnswerMode = 'auto',
  timeoutMs = NON_STREAMING_CHAT_TIMEOUT_MS,
): Promise<{ content: string; intent: string; chapters: string[]; linked_concepts?: ConceptCandidate[]; sources?: AssistantSource[]; conversation_id?: string; turn_id?: string; subject_suggestion?: SubjectRouteSuggestion; rewritten_question?: string; answer_mode?: AnswerMode; suggested_answer_mode?: AnswerMode; scope_reason?: string; use_textbook_context?: boolean }> {
  const res = await apiFetch('/chat/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, book_name: bookName, subject, conversation_id: conversationId, turn_id: turnId, answer_mode: answerMode }),
    signal,
  }, timeoutMs);
  if (!res.ok) throw await responseError(res, 'chatAsk failed');
  return res.json();
}
export async function listAgentTools(includeWrite = false): Promise<AgentToolSpec[]> {
  const res = await get(`/agent/tools?include_write=${includeWrite ? 'true' : 'false'}`);
  return res.data || [];
}

export async function callAgentTool(
  tool: string,
  args: Record<string, unknown> = {},
  bookName = '',
  subject = '',
  conversationId = '',
): Promise<{ success: boolean; tool: string; result: AgentToolResult }> {
  return post('/agent/tools/call', {
    tool,
    args,
    book_name: bookName,
    subject,
    conversation_id: conversationId,
  });
}

export async function runReadOnlyAgent(
  question: string,
  bookName = '',
  subject = '',
  conversationId = '',
  synthesize = true,
  signal?: AbortSignal,
): Promise<ReadOnlyAgentResponse> {
  const res = await apiFetch('/agent/read-only', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      book_name: bookName,
      subject,
      conversation_id: conversationId,
      synthesize,
    }),
    signal,
  }, AGENT_REQUEST_TIMEOUT_MS);
  if (!res.ok) throw await responseError(res, 'Read-only agent failed');
  return res.json();
}
