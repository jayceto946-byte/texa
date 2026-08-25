import { describe, expect, it } from 'vitest';

import { activityDuration, completedActivityCount, mergeChatActivity, settleChatActivity } from './chatActivities';

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

  it.each(['completed', 'failed'] as const)('settles an active resume activity as %s', (status) => {
    const settled = settleChatActivity([
      { id: 'resume', kind: 'system', label: '从检查点恢复', status: 'active' },
      { id: 'evidence', kind: 'evidence', label: '沿用检索证据', status: 'completed' },
    ], 'resume', status, '恢复流程已结束');

    expect(settled[0]).toMatchObject({ status, detail: '恢复流程已结束' });
    expect(settled.some((activity) => activity.status === 'active')).toBe(false);
  });
});
