/** Opt-in, content-free diagnostics. Activated only by ?texa_perf=1. */
import { get } from '../api/client';
import { performanceRecords, resourceEvidence } from './performanceMetrics';
export { resourceCategory } from './performanceMetrics';

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
  button.onclick = async () => {
    button.disabled = true;
    let runtimeBuild = null;
    try { runtimeBuild = (await get('/system/remote-ready?performance=1', 5000))?.data?.runtime_build ?? null; } catch { /* Export remains available when the backend is offline or unauthorized. */ }
    button.disabled = false;
    // Never serialize URLs, queries, credentials, content, user IDs or headers.
    const resources = performance.getEntriesByType('resource').slice(-512).map(entry => resourceEvidence(entry as PerformanceResourceTiming));
    const payload = { schema: 'texa.mobile-performance/v2.1', runtimeBuild, build: document.querySelector<HTMLMetaElement>('meta[name="texa-build"]')?.content || 'unknown', viewport: { width: innerWidth, height: innerHeight }, elapsedMs: performance.now(), observed, resources, metrics: performanceRecords(), navigation: performance.getEntriesByType('navigation').map(entry => { const n = entry as PerformanceNavigationTiming; return { type: n.type, totalMs: n.duration, dnsMs: n.domainLookupEnd - n.domainLookupStart, connectMs: n.connectEnd - n.connectStart, tlsMs: n.secureConnectionStart > 0 ? n.connectEnd - n.secureConnectionStart : 0, requestToHeadersMs: n.responseStart - n.requestStart, headersToBodyMs: n.responseEnd - n.responseStart, wireBytes: n.transferSize, encodedBytes: n.encodedBodySize, decodedBytes: n.decodedBodySize }; }) };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = 'texa-performance.json'; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  document.body.appendChild(button);
}
