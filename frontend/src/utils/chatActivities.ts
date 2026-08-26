import type { ChatActivity, ExecutionEvent } from '../types';

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
  if (currentSeq !== undefined && (incomingSeq === undefined || currentSeq > incomingSeq)) return current;
  return current.map((item, itemIndex) => itemIndex === index ? { ...item, ...incoming } : item);
}

export function projectExecutionEvent(
  current: ChatActivity[] = [],
  event?: ExecutionEvent,
): ChatActivity[] {
  if (!event?.operation_id || !Number.isFinite(event.seq)) return current;
  const connected = current.map((item) => item.id === 'transport' && item.status === 'active'
    ? { ...item, status: 'completed' as const, detail: '执行流已连接' }
    : item);
  const status: ChatActivity['status'] = {
    started: 'active',
    running: 'active',
    completed: 'completed',
    failed: 'failed',
    skipped: 'skipped',
    cancelled: 'skipped',
  }[event.status] as ChatActivity['status'] || 'pending';
  return mergeChatActivity(connected, {
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
  });
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
