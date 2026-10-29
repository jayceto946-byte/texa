import { useEffect } from 'react';
import { get } from '../../api/client';

/** Keep the persistent library route current while an import finishes elsewhere. */
export function useBookCatalogRefresh(enabled: boolean, visible: boolean, refresh: () => Promise<unknown>) {
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const reload = () => { void refresh().catch(() => undefined); };
    const watchImports = async () => {
      try {
        const response = await get('/jobs?type=textbook_import&limit=20');
        if (!active) return;
        const running = response.success && response.data.some((job: { status: string }) => ['queued', 'running', 'cancelling'].includes(job.status));
        reload();
        if (running) timer = setTimeout(() => { void watchImports(); }, 2500);
      } catch { /* The existing library snapshot remains visible. */ }
    };
    window.addEventListener('books:changed', reload);
    if (visible) void watchImports();
    return () => { active = false; clearTimeout(timer); window.removeEventListener('books:changed', reload); };
  }, [enabled, visible, refresh]);
}
