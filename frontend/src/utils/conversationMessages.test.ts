import { describe, expect, it } from 'vitest';
import { mapStoredConversationMessages } from './conversationMessages';

describe('mapStoredConversationMessages', () => {
  it('restores persisted metadata and pairs an assistant with its user question', () => {
    const messages = mapStoredConversationMessages([
      { id: 'u1', turn_id: 't1', role: 'user', content: '什么是矩阵的秩？' },
      {
        id: 'a1',
        turn_id: 't1',
        role: 'assistant',
        content: '矩阵的秩是……',
        answer_mode: 'textbook_grounded',
        request_id: 'req-1',
        answer_feedback: { rating: 'unhelpful', reasons: ['forgot_context'] },
        sources: [{ id: 'E1', label: '教材位置' }],
        citation_provenance: {
          status: 'sources_attached',
          source_attachment_origin: 'system',
          paragraph_alignment: 'unverified',
          automatic_citation_inserted: false,
        },
      },
    ]);

    expect(messages[1]).toMatchObject({
      id: 'a1',
      turnId: 't1',
      role: 'assistant',
      stage: 'done',
      originalQuestion: '什么是矩阵的秩？',
      answerMode: 'textbook_grounded',
      requestId: 'req-1',
      answerFeedback: { rating: 'unhelpful', reasons: ['forgot_context'] },
    });
    expect(messages[1].sources).toHaveLength(1);
    expect(messages[1].citationProvenance).toMatchObject({
      status: 'sources_attached',
      automatic_citation_inserted: false,
    });
  });

  it('does not invent an original question across a pagination boundary', () => {
    const messages = mapStoredConversationMessages([
      { id: 'a2', turn_id: 't2', role: 'assistant', content: '续页回答' },
    ]);

    expect(messages[0].originalQuestion).toBeUndefined();
  });

  it('replays persisted canonical milestones after refresh with the shared lifecycle consumer', () => {
    const messages = mapStoredConversationMessages([{
      id: 'a3', turn_id: 't3', role: 'assistant', content: '已保留的部分回答',
      learning_task: {
        schema_version: 'learning-task/v1', id: 'task-3', task_type: 'qa', goal: '继续回答',
        status: 'interrupted', required_inputs: [], required_outputs: [], terminal: false,
        interruptible: false, resumable: true, input_action_required: false,
        confirmation_required: false,
        artifacts: {
          execution_events: [{
            schema: 'texa.execution/v1', request_id: 'req-3', task_id: 'task-3', run_id: 'run-3',
            conversation_id: 'conversation-3', turn_id: 't3', seq: 1, operation_id: 'pause',
            type: 'state_transition', phase: 'system', status: 'completed', summary: '任务已暂停',
            label: '暂停任务', kind: 'system', elapsed_ms: 10,
            payload: { task_status_before: 'running', task_status_after: 'interrupted' },
          }],
        },
      },
    }]);

    expect(messages[0]).toMatchObject({ stage: 'stopped', content: '已保留的部分回答' });
    expect(messages[0].activities?.[0]).toMatchObject({ id: 'pause', status: 'completed' });
  });
});
