import { expect, it, vi } from 'vitest';
import { createReadCache } from './readCache';

it('shares simultaneous reads, expires success and retries failures', async () => {
  let now = 0;
  const read = vi.fn().mockResolvedValue(['a']);
  const cache = createReadCache(read, 30, () => now);
  await Promise.all([cache.get(), cache.get(), cache.get()]);
  expect(read).toHaveBeenCalledTimes(1);
  await cache.get();
  expect(read).toHaveBeenCalledTimes(1);
  now = 31;
  read.mockRejectedValueOnce(new Error('offline'));
  await expect(cache.get()).rejects.toThrow('offline');
  await cache.get();
  expect(read).toHaveBeenCalledTimes(3);
});

it('rejects stale in-flight results after directory or authorization changes', async () => {
  let resolveOld!: (value: string[]) => void;
  const read = vi.fn().mockImplementationOnce(() => new Promise<string[]>(r => { resolveOld = r; })).mockResolvedValue(['new']);
  const cache = createReadCache<string[]>(read);
  const old = cache.get();
  cache.invalidate();
  expect(await cache.get()).toEqual(['new']);
  resolveOld(['private old source']);
  await expect(old).rejects.toThrow('数据源已更新');
  expect(await cache.get()).toEqual(['new']);
  expect(read).toHaveBeenCalledTimes(2);
});
