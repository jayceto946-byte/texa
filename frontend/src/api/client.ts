import type { AgentPendingAction, AgentToolResult, AgentToolSpec, ReadOnlyAgentResponse, AnswerMode, AssistantSource, ChatActivity, CitationProvenance, ConceptCandidate, ExecutionEvent, LearningTaskState, SubjectRouteSuggestion, VisualRegion } from '../types';

const DEFAULT_TIMEOUT_MS = 20000;
export const AGENT_REQUEST_TIMEOUT_MS = 55000;
export const AGENT_FALLBACK_TIMEOUT_MS = 60000;
const NON_STREAMING_CHAT_TIMEOUT_MS = 130000;
export const IMAGE_SOLUTION_TIMEOUT_MS = 6 * 60 * 1000;
export const IMAGE_RECOGNITION_TIMEOUT_MS = 3 * 60 * 1000;
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
  message_id?: string;
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
  book_name?: string;
  subject?: string;
  resolution_action?: 'continue' | 'clarify' | 'respond';
  subject_suggestion?: SubjectRouteSuggestion;
  rewritten_question?: string;
  use_textbook_context?: boolean;
  scope_reason?: string;
  answer_mode?: AnswerMode;
  suggested_answer_mode?: AnswerMode;
  learning_task?: LearningTaskState;
  retrieval_status?: string;
  retrieval_error?: string;
  activity?: ChatActivity;
  execution_event?: ExecutionEvent;
  result?: {
    success?: boolean;
    explanation?: string;
    linked_concepts?: ConceptCandidate[];
    question_text?: string;
    mistake_id?: string;
    visual_ir?: Record<string, unknown>;
    learning_task?: LearningTaskState;
    sources?: AssistantSource[];
    message_id?: string;
    conversation_id?: string;
    turn_id?: string;
    figure_id?: string;
    region?: number[] | null;
    citation_provenance?: CitationProvenance;
  };
  state?: { linked_concepts?: ConceptCandidate[]; evidence_sources?: AssistantSource[]; suggested_answer_mode?: AnswerMode; learning_task?: LearningTaskState };
};

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const ctrl = new AbortController();
  let timedOut = false;
  let abortedBySource = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    ctrl.abort(new DOMException(`请求超过 ${Math.ceil(timeoutMs / 1000)} 秒`, 'TimeoutError'));
  }, timeoutMs);
  const sourceSignal = init.signal;
  const abortFromSource = () => {
    abortedBySource = true;
    ctrl.abort(sourceSignal?.reason);
  };
  if (sourceSignal?.aborted) abortFromSource();
  else sourceSignal?.addEventListener('abort', abortFromSource, { once: true });
  try {
    return await fetch(input, { ...init, headers: authHeaders(init.headers), signal: ctrl.signal });
  } catch (error) {
    if (timedOut) {
      throw new Error(
        `请求处理超时（${Math.ceil(timeoutMs / 1000)} 秒）。图片识别或模型服务响应较慢，请重试。`,
        { cause: error },
      );
    }
    if (abortedBySource) throw new Error('请求已取消', { cause: error });
    if (error instanceof Error && /signal is aborted|aborterror|aborted/i.test(`${error.name} ${error.message}`)) {
      throw new Error('请求被中止。请确认应用窗口未刷新，并重新提交。', { cause: error });
    }
    throw error;
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
    return event.stage === 'done' || event.stage === 'error' || event.stage === 'waiting_for_input';
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

export function figureQuestionStream(
  payload: {
    book_name: string;
    figure_id: string;
    question: string;
    bbox?: VisualRegion | null;
    subject?: string;
    conversation_id?: string;
    turn_id?: string;
  },
  onEvent: (event: ChatEvent) => void,
  onError?: (error: Error) => void,
): () => void {
  const controller = new AbortController();
  const timer = window.setTimeout(() => {
    controller.abort(new DOMException('教材图片问答超时', 'TimeoutError'));
  }, IMAGE_SOLUTION_TIMEOUT_MS);

  void (async () => {
    try {
      const body = {
        ...payload,
        bbox: payload.bbox
          ? [payload.bbox.x1, payload.bbox.y1, payload.bbox.x2, payload.bbox.y2]
          : null,
      };
      const response = await fetch(apiUrl('/visual-learning/figure-stream'), {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw await responseError(response, '教材图片问答流启动失败');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let terminal = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const parsed = consumeSseChunk(decoder.decode(value, { stream: true }), buffer, onEvent);
        buffer = parsed.buffer;
        terminal = parsed.sawTerminalEvent || terminal;
      }
      buffer += decoder.decode();
      terminal = flushSseBuffer(buffer, onEvent) || terminal;
      if (!terminal && !controller.signal.aborted) throw new Error('教材图片问答流未返回终止事件');
    } catch (error) {
      if (controller.signal.aborted && error instanceof Error && /abort/i.test(error.name)) return;
      onError?.(error instanceof Error ? error : new Error(String(error)));
    } finally {
      window.clearTimeout(timer);
    }
  })();
  return () => {
    window.clearTimeout(timer);
    controller.abort();
  };
}

export function resumeChatTaskStream(
  taskId: string,
  onEvent: (event: ChatEvent) => void,
  onError?: (err: Error) => void,
): () => void {
  const ctrl = new AbortController();
  (async () => {
    try {
      const res = await fetch(apiUrl(`/chat/tasks/${encodeURIComponent(taskId)}/resume-stream`), {
        method: 'POST', headers: authHeaders(), signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw await responseError(res, '恢复任务失败');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let terminal = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const parsed = consumeSseChunk(decoder.decode(value, { stream: true }), buffer, onEvent);
        buffer = parsed.buffer;
        terminal = parsed.sawTerminalEvent || terminal;
      }
      buffer += decoder.decode();
      terminal = flushSseBuffer(buffer, onEvent) || terminal;
      if (!terminal && !ctrl.signal.aborted) throw new Error('恢复流未返回终止事件');
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  })();
  return () => ctrl.abort();
}

export function resumeFigureTaskStream(
  taskId: string,
  onEvent: (event: ChatEvent) => void,
  onError?: (err: Error) => void,
): () => void {
  const ctrl = new AbortController();
  void (async () => {
    try {
      const res = await fetch(apiUrl(`/visual-learning/tasks/${encodeURIComponent(taskId)}/resume-stream`), {
        method: 'POST', headers: authHeaders(), signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw await responseError(res, '恢复 Figure 问答失败');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let terminal = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const parsed = consumeSseChunk(decoder.decode(value, { stream: true }), buffer, onEvent);
        buffer = parsed.buffer;
        terminal = parsed.sawTerminalEvent || terminal;
      }
      buffer += decoder.decode();
      terminal = flushSseBuffer(buffer, onEvent) || terminal;
      if (!terminal && !ctrl.signal.aborted) throw new Error('Figure 恢复流未返回终止事件');
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  })();
  return () => ctrl.abort();
}

export async function interruptFigureTask(
  taskId: string,
  partialOutput = '',
): Promise<{ success: boolean; learning_task: LearningTaskState }> {
  return post(`/visual-learning/tasks/${encodeURIComponent(taskId)}/interrupt`, {
    stage: 'user_stopped', partial_output: partialOutput,
  });
}

export async function interruptChatTask(
  taskId: string,
  partialOutput = '',
): Promise<{ success: boolean; learning_task: LearningTaskState }> {
  return post(`/chat/tasks/${encodeURIComponent(taskId)}/interrupt`, {
    stage: 'user_stopped', partial_output: partialOutput,
  });
}

export function mistakeSolutionStream(
  path: '/mistakes/solve-image-stream' | '/mistakes/solve-cached-stream' | `/mistakes/visual-tasks/${string}/resume-stream`,
  payload: FormData | Record<string, unknown>,
  onEvent: (event: ChatEvent) => void,
  onError?: (error: Error) => void,
): () => void {
  const controller = new AbortController();
  const timer = window.setTimeout(() => {
    controller.abort(new DOMException('图片讲解超时', 'TimeoutError'));
  }, IMAGE_SOLUTION_TIMEOUT_MS);

  (async () => {
    try {
      const isForm = payload instanceof FormData;
      const response = await fetch(apiUrl(path), {
        method: 'POST',
        headers: authHeaders(isForm ? undefined : { 'Content-Type': 'application/json' }),
        body: isForm ? payload : JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw await responseError(response, '图片讲解流启动失败');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let terminal = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const parsed = consumeSseChunk(decoder.decode(value, { stream: true }), buffer, onEvent);
        buffer = parsed.buffer;
        terminal = terminal || parsed.sawTerminalEvent;
      }
      terminal = flushSseBuffer(buffer + decoder.decode(), onEvent) || terminal;
      if (!terminal && !controller.signal.aborted) throw new Error('图片讲解流意外结束');
    } catch (error) {
      if (controller.signal.aborted) {
        if (controller.signal.reason?.name === 'TimeoutError') onError?.(new Error('图片讲解超时，请稍后重试', { cause: error }));
        return;
      }
      onError?.(error instanceof Error ? error : new Error(String(error)));
    } finally {
      window.clearTimeout(timer);
    }
  })();
  return () => controller.abort(new DOMException('用户取消', 'AbortError'));
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
): Promise<{ content: string; intent: string; chapters: string[]; linked_concepts?: ConceptCandidate[]; sources?: AssistantSource[]; conversation_id?: string; turn_id?: string; book_name?: string; subject?: string; request_id?: string; message_id?: string; subject_suggestion?: SubjectRouteSuggestion; rewritten_question?: string; answer_mode?: AnswerMode; suggested_answer_mode?: AnswerMode; scope_reason?: string; use_textbook_context?: boolean }> {
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

export async function resolveAgentAction(
  actionId: string,
  decision: 'confirm' | 'reject',
): Promise<{ success: boolean; action: AgentPendingAction; learning_task?: LearningTaskState | null }> {
  return post(`/agent/actions/${encodeURIComponent(actionId)}/${decision}`, {});
}
