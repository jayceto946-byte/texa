import { useCallback, useEffect, useRef, useState } from 'react';
import { get } from '../api/client';
import type { SystemHealthResponse } from '../types';

export function useSystemHealth(bookName = '', active = true) {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const requestId = useRef(0);

  const loadHealth = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    try {
      const query = bookName ? `?book_name=${encodeURIComponent(bookName)}` : '';
      const nextHealth = await get(`/system/health${query}`, 45000);
      if (currentRequest === requestId.current) setHealth(nextHealth);
    } catch {
      if (currentRequest === requestId.current) {
        setHealth({ status: 'error', book_name: bookName, components: { backend: { status: 'error', message: '\u65e0\u6cd5\u8fde\u63a5\u540e\u7aef\u5065\u5eb7\u68c0\u67e5', details: {} } } });
      }
    } finally {
      if (currentRequest === requestId.current) setLoading(false);
    }
  }, [bookName]);

  useEffect(() => {
    if (!active) return;
    loadHealth();
    const timer = window.setInterval(loadHealth, 30_000);
    return () => window.clearInterval(timer);
  }, [active, loadHealth]);

  return { health, loading, loadHealth };
}
