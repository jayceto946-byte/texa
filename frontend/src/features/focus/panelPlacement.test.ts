import { expect, it } from 'vitest';
import { panelPlacement } from './panelPlacement';
it('opens below the header without covering the chat composer', () => {
  const value = panelPlacement({ width: 1280, mainWidth: 1048, headerBottom: 48, headerRight: 1280, contentBottom: 650 });
  expect(value.sheet).toBe(false);
  expect(value.top).toBeGreaterThan(48);
  expect(value.top + value.maxHeight).toBeLessThan(650);
  expect(value.right).toBe(16);
});
it('uses a dialog when an empty workspace, expanded composer or inspector limits space', () => {
  expect(panelPlacement({ width: 1280, mainWidth: 1048, headerBottom: 48, headerRight: 1280, contentBottom: 340 }).sheet).toBe(true);
  expect(panelPlacement({ width: 1024, mainWidth: 330, headerBottom: 48, headerRight: 700, contentBottom: 700 }).sheet).toBe(true);
  expect(panelPlacement({ width: 760, mainWidth: 760, headerBottom: 56, headerRight: 760, contentBottom: 820 }).sheet).toBe(true);
});
it('anchors to the active workspace when an inspector occupies its right side', () => {
  expect(panelPlacement({ width: 1280, mainWidth: 700, headerBottom: 48, headerRight: 920, contentBottom: 820 }).right).toBe(376);
});
