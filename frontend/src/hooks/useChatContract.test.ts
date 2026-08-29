import { describe, expect, it } from 'vitest';
import client from '../api/client.ts?raw';
import useChat from './useChat.ts?raw';

describe('non-stream chat contract', () => {
  it('projects the backend learning task into the assistant message', () => {
    expect(client).toContain('learning_task?: LearningTaskState');
    expect(useChat).toContain('learningTask: result.learning_task');
  });
});
