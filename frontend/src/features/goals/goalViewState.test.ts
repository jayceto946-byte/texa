import { describe, expect, it } from 'vitest';
import { goalListState, selectedGoalAfterChange, visibleGoals } from './goalViewState';

const goals = [
  {id: 'plain', next_action: null},
  {id: 'scheduled', next_action: {kind: 'schedule'}},
  {id: 'second', next_action: {kind: 'schedule'}},
];

describe('goal collection state', () => {
  it('distinguishes loading, read failure, zero goals and an empty filter', () => {
    expect(goalListState('loading', 0, 0)).toBe('loading');
    expect(goalListState('error', 0, 0)).toBe('error');
    expect(goalListState('ready', 0, 0)).toBe('zero');
    expect(goalListState('ready', 3, 0)).toBe('filtered-empty');
  });

  it('keeps a visible selection and chooses the first match when filtering hides it', () => {
    const scheduled = visibleGoals(goals, 'scheduled');
    expect(scheduled.map((goal) => goal.id)).toEqual(['scheduled', 'second']);
    expect(selectedGoalAfterChange(scheduled, 'second')).toBe('second');
    expect(selectedGoalAfterChange(scheduled, 'plain')).toBe('scheduled');
    expect(selectedGoalAfterChange([], 'plain')).toBe('');
  });
});

import { acceptRuntimeSnapshot } from './goalViewState';

it('ignores delayed snapshots from an older revision or run after a user action', async () => {
  const old = {id: 'task', revision: 2, active_run_id: 'old'};
  let release: (value: typeof old) => void = () => {};
  const delayed = new Promise<typeof old>((resolve) => { release = resolve; });
  let current = old;
  const apply = delayed.then((snapshot) => { if (acceptRuntimeSnapshot(current, snapshot)) current = snapshot; });
  current = {id: 'task', revision: 3, active_run_id: 'new'};
  release(old);
  await apply;
  expect(current.active_run_id).toBe('new');
  expect(acceptRuntimeSnapshot(current, {...current, active_run_id: 'old'})).toBe(false);
  expect(acceptRuntimeSnapshot(current, {...current, revision: 4})).toBe(true);
});

it('orders distinct tasks by creation time and keeps an already loaded task during empty stale polls', () => {
  const current = {id: 'new', revision: 1, created_at: '2026-09-30T12:00:00Z'};
  expect(acceptRuntimeSnapshot(current, {id: 'old', revision: 100, created_at: '2026-09-30T11:00:00Z'})).toBe(false);
  expect(acceptRuntimeSnapshot(current, null)).toBe(false);
});
