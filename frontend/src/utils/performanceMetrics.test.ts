import { afterEach, expect, it, vi } from 'vitest';
import { beginMetric, beginSessionRender, finishSessionRender, performanceRecords, resourceCategory } from './performanceMetrics';
afterEach(() => vi.unstubAllGlobals());
it('does not retain disabled diagnostics or sensitive request values', () => {
  vi.stubGlobal('window', { location: { search: '' } });
  const before = performanceRecords().length;
  beginMetric('finite-request', 'notes')('ok', { decodedBytes: 1024 });
  expect(performanceRecords()).toHaveLength(before);
  expect(resourceCategory('/api/books/private-name/source-pdf')).toBe('textbook-pdf');
  expect(resourceCategory('/api/notes/private-note/revisions/2')).toBe('notes');
  expect(resourceCategory('/api/mistakes/private/attachments/private-photo')).toBe('image');
  expect(resourceCategory('/api/books/private/figures/private/image')).toBe('image');
  expect(resourceCategory('/api/books/private/figures/private')).toBe('citation-read');
});
it('records a bounded single completion, excluding non-numeric fields', () => {
  vi.stubGlobal('window', { location: { search: '?texa_perf=1' } });
  const metric = beginMetric('finite-request', 'notes');
  metric('error', { decodedBytes: 12, headersMs: NaN, ...{ content: 'private-prompt' } });
  metric();
  const item = performanceRecords().at(-1)!;
  expect(item.decodedBytes).toBe(12);
  expect(item.outcome).toBe('error');
  expect(JSON.stringify(item)).not.toContain('private-prompt');
  expect(item).not.toHaveProperty('headersMs');
  for (let i = 0; i < 300; i++) beginMetric('finite-request', 'notes')();
  expect(performanceRecords()).toHaveLength(256);
});
it('fences a replaced Session paint instead of attributing the old frames to a new selection', () => {
  vi.stubGlobal('window', { location: { search: '?texa_perf=1' } });
  vi.stubGlobal('document', { visibilityState: 'visible', querySelector: () => null });
  const frames: FrameRequestCallback[] = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => frames.push(callback));
  beginSessionRender(40); finishSessionRender();
  frames.shift()!(0);
  beginSessionRender(20);
  frames.shift()!(0);
  expect(performanceRecords().at(-1)).toMatchObject({ kind: 'session-render', messages: 40, outcome: 'cancelled' });
  finishSessionRender(); frames.shift()!(0); frames.shift()!(0);
  expect(performanceRecords().at(-1)).toMatchObject({ kind: 'session-render', messages: 20, outcome: 'ok' });
});

it('marks absent response timings unavailable and retains fixed operations only', async () => {
  const { resourceEvidence, resourceOperation } = await import('./performanceMetrics');
  const entry = { name: 'https://private-host/api/jobs/private-job?token=private', startTime: 400, requestStart: 0, responseStart: 0, responseEnd: 20400, duration: 20000, transferSize: 0, encodedBodySize: 0, decodedBodySize: 0, nextHopProtocol: '', serverTiming: [] } as unknown as PerformanceResourceTiming;
  const evidence = resourceEvidence(entry);
  expect(evidence).toMatchObject({ operation: 'job-status', requestToHeadersMs: null, headersToBodyMs: null, delivery: 'unavailable' });
  expect(JSON.stringify(evidence)).not.toContain('private');
  expect(resourceOperation('/api/chat/conversations/private/management')).toBe('session-management');
});
