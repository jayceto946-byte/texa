import { describe, expect, it } from 'vitest';

import { hasUnfilledPlaceholder, templateToEditorLatex } from './formulaEditorUtils';
import type { MathTemplate } from './mathTemplates';

const template = (value: string): MathTemplate => ({ id: 'test', label: 'test', description: 'test', category: 'common', value });

describe('formulaEditorUtils', () => {
  it('removes markdown delimiters and turns internal markers into visual placeholders', () => {
    expect(templateToEditorLatex(template('$\\frac{[[selection|分子]]}{[[cursor|分母]]}$')))
      .toBe('\\frac{\\placeholder{}}{\\placeholder{}}');
  });

  it('detects remaining visual placeholders', () => {
    expect(hasUnfilledPlaceholder('\\sqrt{\\placeholder{}}')).toBe(true);
    expect(hasUnfilledPlaceholder('\\sqrt{x}')).toBe(false);
  });
});
