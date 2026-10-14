import type { FocusSnapshot } from './FocusContext';
export function acceptFocusSnapshot(current: FocusSnapshot | null, next: FocusSnapshot) {
  if (!current) return true;
  if (next.revision !== current.revision) return next.revision > current.revision;
  return next.runtime_id !== current.runtime_id || next.snapshot_sequence > current.snapshot_sequence;
}
export function projectFocus(data: FocusSnapshot | null, received: number, now: number) {
  const elapsed = (data?.active_ms || 0)/1000 + (data?.status === 'running' ? Math.max(0,now-received)/1000 : 0);
  const target = data?.current_session?.target_seconds;
  return {elapsed, remaining: target == null ? null : Math.max(0,target-elapsed), overtime: target == null ? 0 : Math.max(0,elapsed-target)};
}
