import { describe, expect, it } from 'vitest';
import client from '../api/client.ts?raw';
import message from '../components/ChatMessage.tsx?raw';
import chatPage from '../pages/ChatPage.tsx?raw';
import types from '../types/index.ts?raw';
import learningTaskActions from '../components/chat/LearningTaskActions.tsx?raw';
import useChat from './useChat.ts?raw';

describe('non-stream chat contract', () => {
  it('projects the backend learning task into the assistant message', () => {
    expect(client).toContain('learning_task?: LearningTaskState');
    expect(useChat).toContain('learningTask: result.learning_task');
  });

  it('keeps Chat, Figure, and Mistake lifecycle decisions on the canonical consumer', () => {
    for (const consumer of [useChat, chatPage]) {
      expect(consumer).toContain('mergeExecutionLifecycle');
      expect(consumer).not.toMatch(/event\.(stage|chunk|replace|done|activity|message)\b/);
    }
    expect(types).not.toMatch(/(?:type|interface) ChatEvent\b/);
    expect(client).toContain('isExecutionEventV1(event.execution_event)');
    expect(message).toContain('learningTask.input_action_required');
    expect(message).toContain('learningTask?.confirmation_required');
    expect(message).toContain('learningTask?.resumable');
  });

  it('keeps domain sidecars only for non-lifecycle presentation data', () => {
    expect(useChat).toContain('event.state?.evidence_sources');
    expect(useChat).toContain('event.state?.linked_concepts');
    expect(useChat).toContain('event.state?.learning_task');
    expect(chatPage).toContain('event.result?.message_id');
    expect(chatPage).toContain('event.result?.sources');
    expect(chatPage).toContain('event.result?.citation_provenance');
    expect(chatPage).toContain('event.result?.linked_concepts');
    expect(chatPage).toContain('event.result?.learning_task');
  });

  it('keeps pending-action controls without the standalone read-only-agent surface', () => {
    expect(client).not.toContain('/agent/read-only');
    expect(client).not.toContain('/agent/tools');
    expect(message).not.toContain('agentCard');
    expect(types).not.toContain('ReadOnlyAgentResponse');
    expect(types).toContain('interface AgentPendingAction');
    expect(client).toContain('/agent/actions/');
    expect(learningTaskActions).toContain("resolveAgentAction(action.action_id, decision)");
  });
});
