import { describe, expect, it } from 'vitest';

import { insertMathTemplate } from './insertMathTemplate';
import type { MathTemplate } from './mathTemplates';

const template = (value: string): MathTemplate => ({
  id: 'test',
  label: 'test',
  description: 'test',
  category: 'common',
  value,
});

describe('insertMathTemplate', () => {
  it('inserts at the current caret and selects the primary placeholder', () => {
    const result = insertMathTemplate('求值：', 3, 3, template('$\\frac{[[selection|分子]]}{[[cursor|分母]]}$'));

    expect(result.value).toBe('求值：$\\frac{分子}{分母}$');
    expect(result.value.slice(result.selectionStart, result.selectionEnd)).toBe('分子');
  });

  it('wraps selected text and selects the next placeholder', () => {
    const result = insertMathTemplate('计算 x+1', 3, 6, template('$\\frac{[[selection|分子]]}{[[cursor|分母]]}$'));

    expect(result.value).toBe('计算 $\\frac{x+1}{分母}$');
    expect(result.value.slice(result.selectionStart, result.selectionEnd)).toBe('分母');
  });

  it('places the caret after a template without placeholders', () => {
    const result = insertMathTemplate('当 ', 2, 2, template('$\\infty$'));

    expect(result.value).toBe('当 $\\infty$');
    expect(result.selectionStart).toBe(result.value.length);
    expect(result.selectionEnd).toBe(result.value.length);
  });

  it('clamps stale selection offsets safely', () => {
    const result = insertMathTemplate('x', 10, 20, template('$\\alpha$'));
    expect(result.value).toBe('x$\\alpha$');
  });
});
