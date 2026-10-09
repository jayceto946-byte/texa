/** Bounded, opt-in diagnostics. No URL, identity, content or credential is retained. */
export type MetricKind = 'finite-request' | 'text-stream' | 'photo-stream' | 'session-render' | 'asset-preview';
type Numbers = { headersMs?: number; bodyMs?: number; decodedBytes?: number; uploadMs?: number; uploadBytes?: number; firstChunkMs?: number; status?: number; messages?: number };
export type Metric = Numbers & { kind: MetricKind; category: string; startMs: number; totalMs: number; outcome: 'ok' | 'error' | 'cancelled' };
const records: Metric[] = [];
let optedIn = false;
export function performanceEnabled() {
  if (typeof window !== 'undefined' && new URLSearchParams(window.location?.search || '').get('texa_perf') === '1') optedIn = true;
  return optedIn;
}
export function resourceCategory(path: string) {
  if (path === '/api/books/list') return 'book-list';
  if (path === '/api/chat/conversations') return 'session-list';
  if (path.startsWith('/api/chat/conversations/')) return 'session-read';
  if (path === '/api/jobs' || path.startsWith('/api/jobs/')) return 'job-read';
  if (path.startsWith('/api/mistakes')) return /\/(?:image|group-image)$/.test(path) || path.includes('/attachments/') ? 'image' : 'mistake-read';
  if (path.startsWith('/api/exercises')) return 'exercise-read';
  if (path.includes('/chapter-highlights')) return 'chapter-highlight';
  if (path.includes('/figures')) return /\/(?:image|group-image)$/.test(path) ? 'image' : 'citation-read';
  if (path.startsWith('/api/notes')) return 'notes';
  if (path.endsWith('/pdf') || path.endsWith('/source-pdf')) return 'textbook-pdf';
  if (/\/(?:image|group-image)$/.test(path) || path.includes('/attachments/')) return 'image';
  if (path.includes('/figures/') || /\/(?:chapters|sources)(?:\/|$)/.test(path)) return 'citation-read';
  if (path.startsWith('/api/chat/')) return 'chat';
  if (path.startsWith('/api/')) return 'other-api';
  if (/\.(ttf|woff2?)$/.test(path)) return path.includes('Harmony') ? 'harmony-font' : 'other-font';
  if (path.endsWith('.js')) return 'javascript';
  if (path.endsWith('.css')) return 'stylesheet';
  return 'other-resource';
}
/** Fixed operation names let a slow request be identified without exporting its URL/ID/query. */
export function resourceOperation(path: string) {
  if (path === '/api/chat/conversations') return 'session-list';
  if (/^\/api\/chat\/conversations\/[^/]+$/.test(path)) return 'session-detail';
  if (path.startsWith('/api/chat/conversations/') && path.endsWith('/management')) return 'session-management';
  if (path.startsWith('/api/notes/drafts')) return 'note-draft';
  if (path.startsWith('/api/notes') && path.includes('/revisions/')) return 'note-revision';
  if (path === '/api/notes') return 'note-list';
  if (path === '/api/notes/filters') return 'note-filters';
  if (/^\/api\/notes\/[^/]+$/.test(path)) return 'note-read';
  if (path === '/api/jobs') return 'job-list';
  if (path.startsWith('/api/jobs/')) return 'job-status';
  if (path === '/api/system/health') return 'system-health';
  if (path === '/api/system/remote-ready') return 'connection-ready';
  return resourceCategory(path);
}
export function resourceEvidence(timing: PerformanceResourceTiming) {
  const path = new URL(timing.name).pathname;
  const headersAvailable = timing.requestStart > 0 && timing.responseStart > 0;
  return {
    category: resourceCategory(path), operation: resourceOperation(path), startMs: timing.startTime,
    requestToHeadersMs: headersAvailable ? timing.responseStart - timing.requestStart : null,
    headersToBodyMs: timing.responseStart > 0 && timing.responseEnd >= timing.responseStart ? timing.responseEnd - timing.responseStart : null,
    requestQueuedMs: timing.requestStart > 0 ? timing.requestStart - timing.startTime : null,
    totalMs: timing.duration, wireBytes: timing.transferSize,
    encodedBytes: timing.encodedBodySize, decodedBytes: timing.decodedBodySize,
    appHeaderMs: timing.serverTiming?.find(item => item.name === 'texa_read')?.duration ?? null,
    protocol: timing.nextHopProtocol,
    delivery: timing.transferSize > 0 ? 'network' : timing.encodedBodySize > 0 ? 'cache-or-local' : 'unavailable',
  };
}
export function beginMetric(kind: MetricKind, category: ReturnType<typeof resourceCategory>) {
  const enabled = performanceEnabled();
  const startMs = enabled ? performance.now() : 0;
  let ended = false;
  return (outcome: Metric['outcome'] = 'ok', numbers: Numbers = {}) => {
    if (!enabled || ended) return;
    ended = true;
    const fields = ['headersMs', 'bodyMs', 'decodedBytes', 'uploadMs', 'uploadBytes', 'firstChunkMs', 'status', 'messages'];
    const numeric = Object.fromEntries(Object.entries(numbers).filter(([key, value]) => fields.includes(key) && typeof value === 'number' && Number.isFinite(value) && value >= 0));
    records.push({ kind, category, startMs, totalMs: performance.now() - startMs, outcome, ...numeric });
    if (records.length > 256) records.splice(0, records.length - 256);
  };
}
export function performanceRecords() { return records.slice(); }
let sessionPaint: ReturnType<typeof beginMetric> | undefined;
let sessionGeneration = 0;
export function beginSessionRender(messages: number) {
  if (!performanceEnabled()) return;
  sessionPaint?.('cancelled');
  const finish = beginMetric('session-render', 'session-read');
  sessionPaint = outcome => finish(outcome, { messages });
  ++sessionGeneration;
}
/** Called after React commits the selected message array. Includes layout and frame waiting, not pure CPU. */
export function finishSessionRender() {
  if (!performanceEnabled() || !sessionPaint) return;
  const generation = sessionGeneration;
  const deadline = performance.now() + 20000;
  const settle = () => requestAnimationFrame(() => requestAnimationFrame(() => {
    if (generation !== sessionGeneration || !sessionPaint) return;
    const unavailable = document.visibilityState === 'hidden' || performance.now() > deadline;
    // A React commit can still show the lazy Markdown fallback on a cold entry.
    if (!unavailable && document.querySelector('.learning-document-column [data-texa-markdown-loading]')) { settle(); return; }
    sessionPaint(unavailable ? 'cancelled' : 'ok');
    sessionPaint = undefined;
  }));
  settle();
}
