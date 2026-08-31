import { describe, expect, it } from 'vitest';
import client from '../api/client.ts?raw';
import message from '../components/ChatMessage.tsx?raw';
import chatPage from '../pages/ChatPage.tsx?raw';
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
    expect(client).not.toContain('type ChatEvent');
    expect(client).toContain('isExecutionEventV1(event.execution_event)');
    expect(message).toContain('learningTask.input_action_required');
    expect(message).toContain('learningTask?.confirmation_required');
    expect(message).toContain('learningTask?.resumable');
  });
});
