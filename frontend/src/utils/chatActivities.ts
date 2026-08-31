import type {
  ChatActivity,
  ExecutionEvent,
  ExecutionEventStatus,
  ExecutionEventType,
  LearningTaskState,
} from '../types';

const EXECUTION_TYPES = new Set<ExecutionEventType>([
  'progress', 'state_transition', 'tool_result', 'output_delta', 'final', 'error',
]);
const EXECUTION_STATUSES = new Set<ExecutionEventStatus>([
  'started', 'running', 'completed', 'failed', 'skipped', 'cancelled',
]);
const ACTIVITY_KINDS = new Set([
  'analysis', 'tool', 'evidence', 'reasoning', 'generation', 'memory', 'system',
]);
const REQUIRED_EVENT_FIELDS = new Set([
  'schema', 'request_id', 'task_id', 'run_id', 'conversation_id', 'turn_id', 'seq',
  'operation_id', 'type', 'phase', 'status', 'summary', 'label', 'kind', 'elapsed_ms', 'payload',
]);

export interface ExecutionLifecycleState {
  requestId: string;
  taskId: string;
  runId: string;
  conversationId: string;
  turnId: string;
  lastSeq: number;
  retiredRunIds: string[];
  output: string;
  hasOutput: boolean;
  activities: ChatActivity[];
  taskStatus?: string;
  terminal: boolean;
  terminalType?: 'final' | 'error';
  errorCode?: string;
  errorMessage?: string;
  lastEvent?: ExecutionEvent;
}

export function createExecutionLifecycle(
  output = '',
  activities: ChatActivity[] = [],
): ExecutionLifecycleState {
  return {
    requestId: '', taskId: '', runId: '', conversationId: '', turnId: '', lastSeq: 0,
    retiredRunIds: [], output, hasOutput: output.length > 0, activities, terminal: false,
  };
}

export function isExecutionEventV1(value: unknown): value is ExecutionEvent {
  if (!value || typeof value !== 'object') return false;
  const event = value as Partial<ExecutionEvent>;
  const keys = Object.keys(event);
  if ([...REQUIRED_EVENT_FIELDS].some((field) => !keys.includes(field))) return false;
  if (keys.some((field) => !REQUIRED_EVENT_FIELDS.has(field) && field !== 'duration_ms')) return false;
  if (event.schema !== 'texa.execution/v1') return false;
  if (!EXECUTION_TYPES.has(event.type as ExecutionEventType)) return false;
  if (!EXECUTION_STATUSES.has(event.status as ExecutionEventStatus)) return false;
  if (!ACTIVITY_KINDS.has(String(event.kind))) return false;
  if (!Number.isInteger(event.seq) || Number(event.seq) < 1) return false;
  if (typeof event.elapsed_ms !== 'number' || !Number.isFinite(event.elapsed_ms) || event.elapsed_ms < 0) return false;
  if (event.duration_ms !== undefined && (typeof event.duration_ms !== 'number' || !Number.isFinite(event.duration_ms) || event.duration_ms < 0)) return false;
  for (const field of [
    'request_id', 'task_id', 'run_id', 'conversation_id', 'turn_id',
    'operation_id', 'phase', 'summary', 'label', 'kind',
  ] as const) {
    if (typeof event[field] !== 'string') return false;
  }
  if (!event.request_id || Boolean(event.task_id) !== Boolean(event.run_id)) return false;
  if (!event.payload || typeof event.payload !== 'object' || Array.isArray(event.payload)) return false;
  if (event.type === 'output_delta') {
    const keys = Object.keys(event.payload);
    if (keys.length !== 2 || !keys.includes('text') || !keys.includes('replace')) return false;
    if (typeof event.payload.text !== 'string' || typeof event.payload.replace !== 'boolean') return false;
  }
  return true;
}

export function createTransportActivity(): ChatActivity {
  return {
    id: 'transport',
    operation_id: 'transport',
    event_type: 'transport',
    phase: 'transport',
    kind: 'system',
    label: '连接本地执行流',
    status: 'active',
    detail: '正在建立连接，准备接收真实执行事件',
    seq: 0,
  };
}

export function mergeChatActivity(current: ChatActivity[] = [], incoming?: ChatActivity): ChatActivity[] {
  if (!incoming?.id) return current;
  const index = current.findIndex((item) => item.id === incoming.id);
  if (index < 0) return [...current, incoming];
  const currentSeq = current[index].seq;
  const incomingSeq = incoming.seq;
  if (currentSeq !== undefined && (incomingSeq === undefined || currentSeq >= incomingSeq)) return current;
  return current.map((item, itemIndex) => itemIndex === index ? { ...item, ...incoming } : item);
}

function eventActivity(event: ExecutionEvent): ChatActivity {
  const status: ChatActivity['status'] = {
    started: 'active',
    running: 'active',
    completed: 'completed',
    failed: 'failed',
    skipped: 'skipped',
    cancelled: 'skipped',
  }[event.status] as ChatActivity['status'] || 'pending';
  return {
    id: event.operation_id,
    operation_id: event.operation_id,
    event_type: event.type,
    phase: event.phase,
    kind: event.kind,
    label: event.label || event.summary,
    status,
    detail: event.summary,
    duration_ms: event.duration_ms,
    elapsed_ms: event.elapsed_ms,
    seq: event.seq,
    meta: event.payload,
  };
}

function connectedActivities(current: ChatActivity[]): ChatActivity[] {
  return current.map((item) => item.id === 'transport' && item.status === 'active'
    ? { ...item, status: 'completed' as const, detail: '执行流已连接' }
    : item);
}

function terminalActivities(current: ChatActivity[], terminalType: 'final' | 'error', summary: string): ChatActivity[] {
  return current.map((item) => item.status === 'active'
    ? { ...item, status: terminalType === 'final' ? 'completed' as const : 'failed' as const, detail: terminalType === 'final' ? item.detail : summary }
    : item);
}

function eventTaskStatus(event: ExecutionEvent): string | undefined {
  const value = event.payload.task_status_after ?? event.payload.task_status;
  return typeof value === 'string' && value ? value : undefined;
}

function startNewRun(current: ExecutionLifecycleState, event: ExecutionEvent): ExecutionLifecycleState {
  const retiredRunIds = current.runId && current.runId !== event.run_id
    ? [...new Set([...current.retiredRunIds, current.runId])]
    : current.retiredRunIds;
  return {
    ...createExecutionLifecycle(current.output, current.requestId ? [] : current.activities),
    requestId: event.request_id,
    taskId: event.task_id,
    runId: event.run_id,
    conversationId: event.conversation_id,
    turnId: event.turn_id,
    retiredRunIds,
    hasOutput: current.hasOutput,
  };
}

export function mergeExecutionLifecycle(current: ExecutionLifecycleState, candidate: unknown): ExecutionLifecycleState {
  if (!isExecutionEventV1(candidate)) return current;
  const event = candidate;
  if (current.terminal) return current;
  let base = current;

  if (!current.requestId) {
    base = startNewRun(current, event);
  } else if (current.taskId) {
    if (!event.task_id) return current;
    if (event.task_id !== current.taskId) {
      return current;
    } else if (event.run_id !== current.runId) {
      if (current.retiredRunIds.includes(event.run_id)) return current;
      base = startNewRun(current, event);
    } else if (event.request_id !== current.requestId) {
      return current;
    }
  } else if (event.task_id) {
    if (event.request_id !== current.requestId) return current;
    base = { ...current, taskId: event.task_id, runId: event.run_id, conversationId: event.conversation_id, turnId: event.turn_id };
  } else if (event.request_id !== current.requestId) {
    return current;
  }

  if (event.seq <= base.lastSeq) return current;

  let output = base.output;
  if (event.type === 'output_delta') {
    const text = event.payload.text as string;
    output = event.payload.replace ? text : `${output}${text}`;
  }

  const terminalType = event.type === 'final' || event.type === 'error' ? event.type : undefined;
  let activities = connectedActivities(base.activities);
  if (terminalType) activities = terminalActivities(activities, terminalType, event.summary);
  activities = mergeChatActivity(activities, eventActivity(event));
  const errorCode = event.type === 'error' && typeof event.payload.error_code === 'string'
    ? event.payload.error_code
    : base.errorCode;

  return {
    ...base,
    requestId: event.request_id,
    taskId: event.task_id,
    runId: event.run_id,
    conversationId: event.conversation_id,
    turnId: event.turn_id,
    lastSeq: event.seq,
    output,
    hasOutput: base.hasOutput || event.type === 'output_delta',
    activities,
    taskStatus: eventTaskStatus(event) || base.taskStatus,
    terminal: Boolean(terminalType),
    terminalType: terminalType || base.terminalType,
    errorCode,
    errorMessage: event.type === 'error' ? event.summary : base.errorMessage,
    lastEvent: event,
  };
}

export function replayExecutionEvents(events: unknown[], output = ''): ExecutionLifecycleState {
  return events.reduce(mergeExecutionLifecycle, createExecutionLifecycle(output));
}

export function executionMessageStage(lifecycle: ExecutionLifecycleState, task?: LearningTaskState): string {
  if (lifecycle.terminalType === 'error') return 'error';
  if (lifecycle.terminalType === 'final') return 'done';
  if (task?.terminal) return 'done';
  if (task?.input_action_required) return 'waiting_for_input';
  if (task?.resumable) return 'stopped';
  if (lifecycle.lastEvent?.type === 'output_delta') return 'generate';
  return {
    planning: 'plan', retrieval: 'retrieve', evidence: 'chapter', generation: 'generate',
  }[lifecycle.lastEvent?.phase || ''] || 'thinking';
}

export function settleChatActivity(
  current: ChatActivity[] = [],
  id: string,
  status: 'completed' | 'failed',
  detail: string,
): ChatActivity[] {
  return current.map((item) => item.id === id && item.status === 'active'
    ? { ...item, status, detail }
    : item);
}

export function completedActivityCount(activities: ChatActivity[] = []): number {
  return activities.filter((item) => item.status === 'completed' || item.status === 'skipped').length;
}

export function activityDuration(activities: ChatActivity[] = []): number {
  return activities.reduce((total, item) => total + (Number(item.duration_ms) || 0), 0);
}
