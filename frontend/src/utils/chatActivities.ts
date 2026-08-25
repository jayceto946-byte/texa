import type { ChatActivity } from '../types';

export function mergeChatActivity(current: ChatActivity[] = [], incoming?: ChatActivity): ChatActivity[] {
  if (!incoming?.id) return current;
  const index = current.findIndex((item) => item.id === incoming.id);
  if (index < 0) return [...current, incoming];
  return current.map((item, itemIndex) => itemIndex === index ? { ...item, ...incoming } : item);
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
