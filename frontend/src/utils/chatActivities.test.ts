import { describe, expect, it } from 'vitest';

import { activityDuration, completedActivityCount, createExecutionLifecycle, createTransportActivity, mergeChatActivity, mergeExecutionLifecycle, settleChatActivity } from './chatActivities';
import type { ExecutionEvent } from '../types';

function event(overrides: Partial<ExecutionEvent> = {}): ExecutionEvent {
  return {
    schema: 'texa.execution/v1', seq: 1, request_id: 'req', task_id: 'task', run_id: 'run',
    conversation_id: 'conversation', turn_id: 'turn', operation_id: 'operation', type: 'progress',
    phase: 'orchestration', status: 'running', summary: '执行中', label: '执行任务', kind: 'system',
    elapsed_ms: 0, payload: {}, ...overrides,
  };
}

describe('chat activity projection', () => {
  it('shows a truthful transport state before the first backend event', () => {
    const initial = createTransportActivity();
    const connected = mergeExecutionLifecycle(createExecutionLifecycle('', [initial]), event({ operation_id: 'context',
      type: 'progress', phase: 'context', status: 'started', summary: '正在读取上下文',
      label: '读取会话上下文', kind: 'analysis', elapsed_ms: 12,
    }));

    expect(initial).toMatchObject({ id: 'transport', status: 'active' });
    expect(connected.activities[0]).toMatchObject({ id: 'transport', status: 'completed', detail: '执行流已连接' });
    expect(connected.activities[1]).toMatchObject({ id: 'context', elapsed_ms: 12 });
  });

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

  it('projects execution events by operation id and ignores stale sequence updates', () => {
    const started = mergeExecutionLifecycle(createExecutionLifecycle(), event({ seq: 3, operation_id: 'tool:0:math',
      type: 'progress', phase: 'tool', status: 'started', summary: '开始计算',
      label: '执行确定性计算', kind: 'tool',
    }));
    const stale = mergeExecutionLifecycle(started, event({ seq: 2, operation_id: 'tool:0:math',
      type: 'progress', phase: 'tool', status: 'running', summary: '旧进度',
      label: '执行确定性计算', kind: 'tool',
    }));
    const completed = mergeExecutionLifecycle(stale, event({ seq: 4, operation_id: 'tool:0:math',
      type: 'tool_result', phase: 'tool', status: 'completed', summary: '计算完成',
      label: '执行确定性计算', kind: 'tool',
    }));
    const legacyAfterSequenced = mergeChatActivity(completed.activities, {
      id: 'tool:0:math', kind: 'tool', label: '旧事件', status: 'active', detail: '旧状态',
    });

    expect(stale.activities[0].detail).toBe('开始计算');
    expect(completed.activities[0]).toMatchObject({ status: 'completed', detail: '计算完成', seq: 4 });
    expect(legacyAfterSequenced[0]).toMatchObject({ status: 'completed', detail: '计算完成', seq: 4 });
  });
});
