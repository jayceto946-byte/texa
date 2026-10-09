/** Opt-in, content-free diagnostics. Activated only by ?texa_perf=1. */
export function resourceCategory(path: string) {
  if (path === '/api/books/list') return 'book-list';
  if (path.startsWith('/api/chat/conversations/')) return 'session-read';
  if (path.startsWith('/api/chat/')) return 'chat';
  if (path.endsWith('/pdf')) return 'textbook-pdf';
  if (path.includes('/image')) return 'image';
  if (path.startsWith('/api/')) return 'other-api';
  if (/\.(ttf|woff2?)$/.test(path)) return path.includes('Harmony') ? 'harmony-font' : 'other-font';
  if (path.endsWith('.js')) return 'javascript';
  if (path.endsWith('.css')) return 'stylesheet';
  return 'other-resource';
}

export function installMobilePerformance() {
  performance.setResourceTimingBufferSize(512);
  const observed: { type: string; startMs: number; durationMs: number }[] = [];
  for (const type of ['paint', 'largest-contentful-paint', 'longtask']) {
    try {
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) observed.push({ type: entry.entryType, startMs: entry.startTime, durationMs: entry.duration });
        if (observed.length > 256) observed.splice(0, observed.length - 256);
      }).observe({ type, buffered: true });
    } catch { /* Browser does not support this observer type. */ }
  }
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = '导出性能记录';
  button.setAttribute('aria-label', '导出仅含耗时与尺寸的性能记录');
  Object.assign(button.style, { position: 'fixed', top: '0', right: '0', zIndex: '1000', minHeight: '44px', padding: '8px', background: '#fff', color: '#222', border: '1px solid #888' });
  button.onclick = () => {
    // Never serialize URLs, queries, credentials, content, user IDs or headers.
    const resources = performance.getEntriesByType('resource').slice(-512).map(entry => {
      const timing = entry as PerformanceResourceTiming;
      const path = new URL(timing.name).pathname;
      return {
        category: resourceCategory(path), startMs: timing.startTime,
        requestToHeadersMs: timing.responseStart - timing.requestStart,
        headersToBodyMs: timing.responseEnd - timing.responseStart,
        totalMs: timing.duration, wireBytes: timing.transferSize,
        encodedBytes: timing.encodedBodySize, decodedBytes: timing.decodedBodySize,
        appHeaderMs: timing.serverTiming?.find(item => item.name === 'texa_read')?.duration ?? null,
        protocol: timing.nextHopProtocol,
      };
    });
    const payload = { schema: 'texa.mobile-performance/v1', build: document.querySelector<HTMLMetaElement>('meta[name="texa-build"]')?.content || 'unknown', viewport: { width: innerWidth, height: innerHeight }, elapsedMs: performance.now(), observed, resources };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = 'texa-performance.json'; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  document.body.appendChild(button);
}
