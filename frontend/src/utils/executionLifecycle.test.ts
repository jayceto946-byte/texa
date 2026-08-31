import { describe, expect, it } from 'vitest';

import type { ExecutionEvent, LearningTaskState } from '../types';
import {
  createExecutionLifecycle,
  executionMessageStage,
  isExecutionEventV1,
  mergeExecutionLifecycle,
  replayExecutionEvents,
} from './chatActivities';

function fixture(overrides: Partial<ExecutionEvent> = {}): ExecutionEvent {
  return {
    schema: 'texa.execution/v1',
    request_id: 'req-chat',
    task_id: 'task-chat',
    run_id: 'run-1',
    conversation_id: 'conversation-1',
    turn_id: 'turn-1',
    seq: 1,
    operation_id: 'context',
    type: 'progress',
    phase: 'context',
    status: 'running',
    summary: '执行中',
    label: '执行任务',
    kind: 'system',
    elapsed_ms: 1,
    payload: {},
    ...overrides,
  };
}

function task(overrides: Partial<LearningTaskState> = {}): LearningTaskState {
  return {
    schema_version: 'learning-task/v1', id: 'task-chat', task_type: 'qa', goal: '回答问题',
    status: 'running', required_inputs: [], required_outputs: [], terminal: false,
    interruptible: true, resumable: false, input_action_required: false,
    confirmation_required: false, ...overrides,
  };
}

describe('ExecutionEvent V1 lifecycle consumer', () => {
  it('accepts Chat, Figure, and taskless Mistake canonical identities', () => {
    const chat = fixture();
    const figure = fixture({ request_id: 'req-figure', task_id: 'task-figure', run_id: 'run-figure', phase: 'evidence' });
    const mistake = fixture({ request_id: 'req-mistake', task_id: '', run_id: '', conversation_id: '', turn_id: '', phase: 'input' });

    expect(isExecutionEventV1(chat)).toBe(true);
    expect(isExecutionEventV1(figure)).toBe(true);
    expect(isExecutionEventV1(mistake)).toBe(true);
    expect(mergeExecutionLifecycle(createExecutionLifecycle(), mistake)).toMatchObject({ taskId: '', runId: '', lastSeq: 1 });
  });

  it('applies output append and replace only from canonical payload', () => {
    const events = [
      fixture({ seq: 1, type: 'output_delta', phase: 'generation', operation_id: 'answer', payload: { text: 'A', replace: false } }),
      fixture({ seq: 2, type: 'output_delta', phase: 'generation', operation_id: 'answer', payload: { text: 'B', replace: false } }),
      fixture({ seq: 3, type: 'output_delta', phase: 'generation', operation_id: 'verify', payload: { text: 'verified', replace: true } }),
    ];
    expect(replayExecutionEvents(events).output).toBe('verified');
    const cleared = mergeExecutionLifecycle(replayExecutionEvents(events), fixture({
      seq: 4, type: 'output_delta', phase: 'generation', operation_id: 'verify',
      payload: { text: '', replace: true },
    }));
    expect(cleared).toMatchObject({ output: '', hasOutput: true });
  });

  it('ignores decreasing and duplicate seq values', () => {
    const accepted = mergeExecutionLifecycle(createExecutionLifecycle(), fixture({ seq: 3, summary: 'current' }));
    const stale = mergeExecutionLifecycle(accepted, fixture({ seq: 2, summary: 'stale' }));
    const duplicate = mergeExecutionLifecycle(accepted, fixture({ seq: 3, summary: 'duplicate' }));
    expect(stale).toBe(accepted);
    expect(duplicate).toBe(accepted);
    expect(accepted.lastEvent?.summary).toBe('current');
  });

  it('switches to a new run and rejects late events from the retired run', () => {
    const run1 = mergeExecutionLifecycle(createExecutionLifecycle(), fixture({ seq: 4, run_id: 'run-1' }));
    const run2 = mergeExecutionLifecycle(run1, fixture({ seq: 1, request_id: 'req-resume', run_id: 'run-2', operation_id: 'resume' }));
    const lateRun1 = mergeExecutionLifecycle(run2, fixture({ seq: 5, run_id: 'run-1', summary: 'late' }));

    expect(run2).toMatchObject({ runId: 'run-2', lastSeq: 1, retiredRunIds: ['run-1'] });
    expect(lateRun1).toBe(run2);
  });

  it('accepts one terminal and ignores all later events in that run', () => {
    const final = mergeExecutionLifecycle(createExecutionLifecycle(), fixture({
      type: 'final', status: 'completed', phase: 'final', payload: { task_status: 'degraded' },
    }));
    const duplicateFinal = mergeExecutionLifecycle(final, fixture({ seq: 2, type: 'final', status: 'completed', phase: 'final', payload: { task_status: 'degraded' } }));
    const lateDelta = mergeExecutionLifecycle(final, fixture({ seq: 3, type: 'output_delta', phase: 'generation', payload: { text: 'late', replace: false } }));
    const lateRun = mergeExecutionLifecycle(final, fixture({ seq: 1, request_id: 'req-late', run_id: 'run-late' }));

    expect(final).toMatchObject({ terminal: true, terminalType: 'final', taskStatus: 'degraded' });
    expect(duplicateFinal).toBe(final);
    expect(lateDelta).toBe(final);
    expect(lateRun).toBe(final);
  });

  it('derives waiting, confirmation, interrupt, and resume UI state from canonical/task flags', () => {
    const waiting = mergeExecutionLifecycle(createExecutionLifecycle(), fixture({
      type: 'state_transition', phase: 'input', status: 'completed',
      payload: { task_status_before: 'running', task_status_after: 'waiting_for_input' },
    }));
    expect(waiting.taskStatus).toBe('waiting_for_input');
    expect(executionMessageStage(waiting, task({ input_action_required: true, interruptible: false }))).toBe('waiting_for_input');

    const confirmation = task({ status: 'waiting_for_confirmation', interruptible: false, confirmation_required: true });
    expect(confirmation.confirmation_required).toBe(true);

    const interrupted = mergeExecutionLifecycle(createExecutionLifecycle(), fixture({
      type: 'state_transition', phase: 'system', status: 'completed',
      payload: { task_status_before: 'running', task_status_after: 'interrupted' },
    }));
    expect(executionMessageStage(interrupted, task({ status: 'interrupted', interruptible: false, resumable: true }))).toBe('stopped');
    const resumed = mergeExecutionLifecycle(interrupted, fixture({
      seq: 1, request_id: 'req-resume', run_id: 'run-2', type: 'state_transition',
      payload: { task_status_before: 'interrupted', task_status_after: 'running' },
    }));
    expect(resumed).toMatchObject({ runId: 'run-2', taskStatus: 'running', terminal: false });
  });

  it('reads Figure 409 identity from canonical error payload', () => {
    const failed = mergeExecutionLifecycle(createExecutionLifecycle(), fixture({
      request_id: 'req-figure', task_id: 'task-figure', run_id: 'run-figure',
      type: 'error', phase: 'error', status: 'failed', summary: 'active index is stale',
      payload: { task_status: 'failed', error_code: 'figure_index_out_of_date', http_status: 409 },
    }));
    expect(failed).toMatchObject({ terminalType: 'error', errorCode: 'figure_index_out_of_date', errorMessage: 'active index is stale' });
  });

  it('rejects the removed tool_call type and malformed output payload', () => {
    expect(isExecutionEventV1({ ...fixture(), type: 'tool_call' })).toBe(false);
    expect(isExecutionEventV1({ ...fixture(), type: 'output_delta', payload: { text: 'x', replace: false, chunk: 'legacy' } })).toBe(false);
    expect(isExecutionEventV1({ ...fixture(), stage: 'done' })).toBe(false);
  });
});
