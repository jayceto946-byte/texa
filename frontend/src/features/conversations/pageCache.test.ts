import { describe, expect, it } from 'vitest';
import { createConversationPageCache } from './pageCache';
import type { ConversationListPage } from './api';
const page = (id: string): ConversationListPage => ({ items: [{ id, title: id, subject: '', book_name: '', updated_at: '', message_count: 2, management: { state: 'active', pinned: false, revision: 0 } }], next_cursor: 'next', has_more: true });
describe('history page cache', () => {
  it('isolates view and textbook scopes, and keeps cursor with its own rows', () => {
    const cache = createConversationPageCache();
    cache.set('view=active&book_name=A', page('a'));
    cache.set('view=archived&book_name=A', page('b'));
    expect(cache.fresh('view=active&book_name=A')).toEqual(page('a'));
    expect(cache.fresh('view=archived&book_name=A')).toEqual(page('b'));
    expect(cache.peek('view=active&book_name=B')).toBeUndefined();
  });
  it('retains expired rows for display while requiring revalidation', () => {
    let now = 0;
    const cache = createConversationPageCache(() => now, 100);
    cache.set('active', page('a')); now = 101;
    expect(cache.fresh('active')).toBeUndefined();
    expect(cache.peek('active')).toEqual(page('a'));
    cache.clear(); expect(cache.peek('active')).toBeUndefined();
  });
  it('bounds memory and replaces paginated snapshots atomically', () => {
    const cache = createConversationPageCache(Date.now, 100, 2);
    cache.set('a', page('a')); cache.set('b', page('b')); cache.set('c', page('c'));
    expect(cache.peek('a')).toBeUndefined();
    cache.set('b', { items: [], next_cursor: null, has_more: false });
    expect(cache.fresh('b')).toEqual({ items: [], next_cursor: null, has_more: false });
    cache.clear(); expect(cache.fresh('b')).toBeUndefined();
  });
});
