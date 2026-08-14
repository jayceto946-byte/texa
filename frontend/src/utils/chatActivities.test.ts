import { describe, expect, it } from 'vitest';

import { activityDuration, completedActivityCount, mergeChatActivity } from './chatActivities';

describe('chat activity projection', () => {
  it('updates an existing activity without reordering it', () => {
    const started = mergeChatActivity([], { id: 'vision', kind: 'tool', label: '识别图片', status: 'active' });
    const completed = mergeChatActivity(started, { id: 'vision', kind: 'tool', label: '识别图片', status: 'completed', duration_ms: 1200 });
    expect(completed).toHaveLength(1);
    expect(completed[0].status).toBe('completed');
    expect(activityDuration(completed)).toBe(1200);
  });

  it('counts completed and skipped work as settled', () => {
    expect(completedActivityCount([
      { id: 'a', kind: 'analysis', label: 'A', status: 'completed' },
      { id: 'b', kind: 'tool', label: 'B', status: 'skipped' },
      { id: 'c', kind: 'generation', label: 'C', status: 'active' },
    ])).toBe(2);
  });
});
