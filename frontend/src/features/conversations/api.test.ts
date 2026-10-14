import { afterEach, expect, it, vi } from 'vitest';
import { ConversationError, conversationApi } from './api';

afterEach(() => vi.unstubAllGlobals());
function prepare(payload: unknown, status = 200) {
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('window', { setTimeout, clearTimeout, localStorage: { getItem: () => null } });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

it('preserves a stable cursor and repeated textbook scopes in paginated history requests', async () => {
  const page = { items: [], next_cursor: 'snapshot-next', has_more: true };
  const fetch = prepare({ success: true, data: page });
  const query = new URLSearchParams({ view: 'archived', limit: '40', cursor: 'snapshot-start' });
  query.append('book_names', '高等数学上'); query.append('book_names', '高等数学下');
  expect(await conversationApi.list(query.toString())).toEqual(page);
  const url = new URL(fetch.mock.calls[0][0], 'http://localhost');
  expect(url.searchParams.getAll('book_names')).toEqual(['高等数学上', '高等数学下']);
  expect(url.searchParams.get('cursor')).toBe('snapshot-start');
});

it('passes the same operation receipt and revision when retrying a recoverable delete', async () => {
  const fetch = prepare({ success: true, data: { state: 'trashed', pinned: false, revision: 8 } });
  await conversationApi.change('old conversation', 'trash', 7, 'stable-operation');
  await conversationApi.change('old conversation', 'trash', 7, 'stable-operation');
  expect(fetch.mock.calls[0][0]).toContain('/old%20conversation/management');
  const first = JSON.parse(fetch.mock.calls[0][1].body);
  expect(first).toEqual({ action: 'trash', expected_revision: 7, operation_id: 'stable-operation' });
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual(first);
});

it('keeps task identity and the explicit cancellation choice on a busy response', async () => {
  const tasks = [{ id: 'task', status: 'interrupted', run_id: 'run', revision: 4, can_cancel: true }];
  prepare({ success: false, code: 'conversation_busy', message: '请先处理未完成任务', tasks }, 409);
  try {
    await conversationApi.change('conversation', 'archive', 0, 'archive-op');
    throw new Error('expected a busy response');
  } catch (error) {
    expect(error).toBeInstanceOf(ConversationError);
    expect(error).toMatchObject({ code: 'conversation_busy', tasks });
  }
});
