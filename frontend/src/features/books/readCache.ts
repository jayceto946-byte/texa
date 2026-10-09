/** A successful, short-lived snapshot and one read per invalidation generation. */
export function createReadCache<T>(read: () => Promise<T>, ttlMs = 30_000, now = Date.now) {
  let generation = 0;
  let snapshot: { value: T; expires: number } | undefined;
  let pending: Promise<T> | undefined;
  return {
    invalidate() { generation++; snapshot = undefined; pending = undefined; },
    async get(): Promise<T> {
      if (snapshot && snapshot.expires > now()) return snapshot.value;
      if (pending) return pending;
      const current = generation;
      const request = read().then(value => {
        if (current !== generation) throw new Error('读取期间数据源已更新，请重新读取');
        snapshot = { value, expires: now() + ttlMs };
        return value;
      }).finally(() => { if (pending === request) pending = undefined; });
      pending = request;
      return request;
    },
  };
}
