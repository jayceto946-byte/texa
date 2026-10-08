import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { afterEach, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ remote: true, workspaceLoaded: vi.fn() }));
vi.mock('./api/client', () => ({
  isRemoteBrowser: () => state.remote,
  get: vi.fn(),
  setConnectionToken: vi.fn(),
}));
vi.mock('./Workspace', () => {
  state.workspaceLoaded();
  return { default: () => createElement('div', null, 'workspace-ready') };
});
afterEach(() => { vi.resetModules(); state.workspaceLoaded.mockClear(); state.remote = true; });

it('shows the remote connection gate without importing the authenticated workspace', async () => {
  const { default: App } = await import('./App');
  const html = renderToString(createElement(App));
  expect(html).toContain('连接 Texa Desktop');
  expect(html).not.toContain('workspace-ready');
  await Promise.resolve();
  expect(state.workspaceLoaded).not.toHaveBeenCalled();
});
it('opens the workspace on desktop with a visible loading state', async () => {
  state.remote = false;
  const { default: App } = await import('./App');
  expect(renderToString(createElement(App))).toContain('正在加载学习工作区');
  await vi.waitFor(() => expect(state.workspaceLoaded).toHaveBeenCalledOnce());
  expect(renderToString(createElement(App))).toContain('workspace-ready');
});
