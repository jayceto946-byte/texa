import { expect, it } from 'vitest';
import { scopePopoverLayout } from './scopePopover';

const base = { anchor: { left: 960, right: 1240, top: 12, bottom: 44 }, viewport: { width: 1280, height: 820 }, subjectOnly: false, compact: false, placement: 'bottom' as const, align: 'right' as const };
it('fits a header popup against the right edge without stretching to the viewport', () => {
  expect(scopePopoverLayout(base)).toMatchObject({ width: 620, left: 620, maxHeight: 360, openAbove: false, layout: 'books' });
});
it('uses a smaller two-column popup for the history drawer', () => {
  expect(scopePopoverLayout({ ...base, anchor: { left: 16, right: 288, top: 140, bottom: 172 }, subjectOnly: true, compact: true, align: 'left' })).toMatchObject({ width: 320, left: 16, maxHeight: 320, layout: 'subjects' });
});
it('flips above a low form field and keeps all bounds inside a short viewport', () => {
  const result = scopePopoverLayout({ ...base, anchor: { left: 840, right: 1160, top: 650, bottom: 686 }, viewport: { width: 1024, height: 768 } });
  expect(result.openAbove).toBe(true);
  expect(result.left + result.width).toBeLessThanOrEqual(1012);
  expect(result.edge + result.maxHeight).toBeLessThanOrEqual(756);
});
it('wraps textbooks under subjects in narrow windows, with no minimum height overflow', () => {
  const result = scopePopoverLayout({ ...base, anchor: { left: 16, right: 300, top: 112, bottom: 148 }, viewport: { width: 390, height: 320 }, align: 'left' });
  expect(result).toMatchObject({ width: 366, left: 12, layout: 'wrapped', openAbove: false, maxHeight: 154 });
  expect(result.edge + result.maxHeight).toBe(308);
});
