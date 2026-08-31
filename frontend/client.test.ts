import { afterEach, describe, expect, it, vi } from 'vitest';
import { consumeSseChunk, consumeSseLine, flushSseBuffer } from './src/api/client';
import type { ExecutionEvent, ExecutionStreamEnvelope } from './src/types';

function envelope(eventOverrides: Partial<ExecutionEvent> = {}): ExecutionStreamEnvelope {
  return {
    execution_event: {
      schema: 'texa.execution/v1', request_id: 'req', task_id: 'task', run_id: 'run',
      conversation_id: 'conversation', turn_id: 'turn', seq: 1, operation_id: 'answer',
      type: 'output_delta', phase: 'generation', status: 'running', summary: '生成回答',
      label: '生成回答', kind: 'generation', elapsed_ms: 1,
      payload: { text: 'hello', replace: false }, ...eventOverrides,
    },
  };
}

describe('SSE parsing', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps partial data in the buffer until a newline completes the event', () => {
    const events: ExecutionStreamEnvelope[] = [];
    const payload = JSON.stringify(envelope());
    const splitAt = payload.indexOf('hello') + 2;
    const first = consumeSseChunk(`data: ${payload.slice(0, splitAt)}`, '', (event) => events.push(event));

    expect(first.buffer).toBe(`data: ${payload.slice(0, splitAt)}`);
    expect(first.sawBoundaryEvent).toBe(false);
    expect(events).toEqual([]);

    const second = consumeSseChunk(`${payload.slice(splitAt)}\n\n`, first.buffer, (event) => events.push(event));

    expect(second.buffer).toBe('');
    expect(second.sawBoundaryEvent).toBe(false);
    expect(events).toEqual([envelope()]);
  });

  it('detects done and error terminal events', () => {
    const events: ExecutionStreamEnvelope[] = [];

    expect(consumeSseLine(`data: ${JSON.stringify(envelope({ type: 'final', phase: 'final', status: 'completed', payload: {} }))}`, (event) => events.push(event))).toBe(true);
    expect(consumeSseLine(`data: ${JSON.stringify(envelope({ seq: 2, type: 'error', phase: 'error', status: 'failed', payload: { error_code: 'bad' } }))}`, (event) => events.push(event))).toBe(true);

    expect(events.map((event) => event.execution_event.type)).toEqual(['final', 'error']);
  });

  it('flushes a residual final line after the stream closes', () => {
    const events: ExecutionStreamEnvelope[] = [];

    const final = envelope({ type: 'final', phase: 'final', status: 'completed', payload: {} });
    const sawTerminal = flushSseBuffer(`data: ${JSON.stringify(final)}`, (event) => events.push(event));

    expect(sawTerminal).toBe(true);
    expect(events).toEqual([final]);
  });

  it('warns and skips malformed JSON payloads', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const events: ExecutionStreamEnvelope[] = [];

    const sawTerminal = consumeSseLine('data: {not-json}', (event) => events.push(event));

    expect(sawTerminal).toBe(false);
    expect(events).toEqual([]);
    expect(warn).toHaveBeenCalled();
  });

  it('treats canonical waiting_for_input as a valid paused stream boundary', () => {
    const waiting = envelope({
      type: 'state_transition', phase: 'input', status: 'completed',
      payload: { task_status_before: 'running', task_status_after: 'waiting_for_input' },
    });
    expect(consumeSseLine(`data: ${JSON.stringify(waiting)}`, () => undefined)).toBe(true);
  });

  it('does not treat a legacy DONE sentinel as canonical termination', () => {
    expect(consumeSseLine('data: [DONE]', () => undefined)).toBe(false);
  });
});
