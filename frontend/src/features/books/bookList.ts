import { get, onConnectionChange } from '../../api/client';
import { createReadCache } from './readCache';
import type { BookInfo } from '../../types';

const cache = createReadCache(async (): Promise<{ success: true; data: BookInfo[] }> => {
  const result = await get('/books/list');
  if (!result?.success || !Array.isArray(result.data)) throw new Error('无法读取教材目录');
  return { success: true, data: result.data };
});

// Register once, before consumer listeners. No private snapshots in localStorage.
if (typeof window !== 'undefined') {
  window.addEventListener('books:changed', () => cache.invalidate());
}
onConnectionChange(() => cache.invalidate());

export const getBookList = () => cache.get();
