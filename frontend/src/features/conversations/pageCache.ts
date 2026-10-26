import type { ConversationListPage } from './api';

/** Memory only, bounded by scope and view; never caches conversation bodies. */
export function createConversationPageCache(now = Date.now, ttlMs = 30_000, capacity = 12) {
  const pages = new Map<string, { page: ConversationListPage; expires: number }>();
  return {
    peek(query: string) { return pages.get(query)?.page; },
    fresh(query: string) {
      const entry = pages.get(query);
      return entry && entry.expires > now() ? entry.page : undefined;
    },
    set(query: string, page: ConversationListPage) {
      pages.delete(query);
      pages.set(query, { page, expires: now() + ttlMs });
      while (pages.size > capacity) pages.delete(pages.keys().next().value!);
    },
    clear() { pages.clear(); },
  };
}
