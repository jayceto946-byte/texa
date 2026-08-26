import { describe, expect, it } from 'vitest';
import { formatLearningScopeLabel } from './textbookScopes';

describe('formatLearningScopeLabel', () => {
  it('does not repeat a logical scope that matches the subject leaf', () => {
    expect(formatLearningScopeLabel('专业课/传感器', '传感器')).toBe('专业课 / 传感器');
  });

  it('keeps a distinct textbook name as secondary scope information', () => {
    expect(formatLearningScopeLabel('专业课/传感器', '传感器短书')).toBe('专业课 / 传感器 · 传感器短书');
  });

  it('keeps the general QA fallback without duplicating separators', () => {
    expect(formatLearningScopeLabel('数学/线代', '通用问答')).toBe('数学 / 线代 · 通用问答');
  });
});
