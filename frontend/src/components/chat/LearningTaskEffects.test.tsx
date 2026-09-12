import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { LearningTaskState } from '../../types';
import LearningTaskEffects from './LearningTaskEffects';

function task(effects?: unknown): LearningTaskState {
  return { id: 'task', active_run_id: 'run', schema_version: 'learning-task/v1', task_type: 'visual_qa',
    goal: 'answer', status: 'completed', required_inputs: [], required_outputs: [], artifacts: { effects },
    terminal: true, interruptible: false, resumable: false, input_action_required: false, confirmation_required: false };
}

describe('committed learning record status', () => {
  it('does not claim import while a receipt is missing, even if a tentative id exists', () => {
    const html = renderToStaticMarkup(<LearningTaskEffects task={task([
      { id: 'effect', status: 'pending', result: { mistake_id: 'tentative' } },
    ])} />);
    expect(html).toContain('答案已保存，学习记录待恢复');
    expect(html).not.toContain('已导入错题本');
    expect(html).not.toContain('<button');
    expect(html).toContain('role="status"');
  });

  it('shows import only with a completed receipt', () => {
    const html = renderToStaticMarkup(<LearningTaskEffects task={task([
      { id: 'effect', status: 'completed', result: { mistake_id: 'saved' } },
    ])} />);
    expect(html).toContain('已导入错题本');
    expect(html).not.toContain('待恢复');
  });

  it('keeps legacy tasks and completed background feedback quiet', () => {
    for (const value of [undefined, [], [{ id: 'effect', status: 'completed', result: { concept_count: 1 } }]]) {
      expect(renderToStaticMarkup(<LearningTaskEffects task={task(value)} />)).toBe('');
    }
  });
});
