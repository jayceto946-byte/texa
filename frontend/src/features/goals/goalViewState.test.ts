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
