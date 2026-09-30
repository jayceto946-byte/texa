export type GoalFilter = 'all' | 'scheduled';
export type GoalListStatus = 'loading' | 'ready' | 'error';
export type GoalListState = 'loading' | 'error' | 'zero' | 'filtered-empty' | 'populated';

export function visibleGoals<T extends { next_action?: {kind: string} | null }>(goals: T[], filter: GoalFilter): T[] {
  return filter === 'all' ? goals : goals.filter((goal) => goal.next_action?.kind === 'schedule');
}

export function goalListState(status: GoalListStatus, total: number, visible: number): GoalListState {
  if (status !== 'ready') return status;
  if (total === 0) return 'zero';
  return visible === 0 ? 'filtered-empty' : 'populated';
}

export function selectedGoalAfterChange<T extends { id: string }>(visible: T[], selected: string): string {
  return visible.some((goal) => goal.id === selected) ? selected : (visible[0]?.id || '');
}

// Revisions are authoritative within a task; created_at orders distinct tasks.
export function acceptRuntimeSnapshot(current: {id: string; revision?: number; active_run_id?: string; created_at?: string} | null,
  next: {id: string; revision?: number; active_run_id?: string; created_at?: string} | null): boolean {
  if (!current) return true;
  if (!next) return false;
  if (current.id !== next.id) return (next.created_at || '') >= (current.created_at || '');
  if ((next.revision || 0) < (current.revision || 0)) return false;
  if (next.revision === current.revision && next.active_run_id !== current.active_run_id) return false;
  return true;
}
