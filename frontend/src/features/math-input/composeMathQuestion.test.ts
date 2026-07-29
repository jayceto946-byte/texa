import { describe, expect, it } from 'vitest';

import { composeMathQuestion } from './composeMathQuestion';

describe('composeMathQuestion', () => {
  it('adds an explicit compact-number mapping for user formula references', () => {
    expect(composeMathQuestion('请用公式2计算，并与公式1比较', [
      { id: 'a', latex: '\\frac{1}{2}', displayMode: false, referenceNumber: 1 },
      { id: 'b', latex: '\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}', displayMode: true, referenceNumber: 2 },
    ])).toBe([
      '请用公式2计算，并与公式1比较',
      '以下编号与问题中的“公式1”“公式2”等称呼一一对应：',
      '公式1：$\\frac{1}{2}$',
      '公式2：\n\n$$\n\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}\n$$',
    ].join('\n\n'));
  });

  it('allows sending a formula without ordinary text', () => {
    expect(composeMathQuestion('', [{ id: 'a', latex: 'x^2', displayMode: false }])).toBe(
      '以下编号与问题中的“公式1”“公式2”等称呼一一对应：\n\n公式1：$x^2$',
    );
  });

  it('skips empty expressions', () => {
    expect(composeMathQuestion('问题', [{ id: 'a', latex: '  ', displayMode: true }])).toBe('问题');
  });

  it('keeps stable reference numbers after an earlier formula is removed', () => {
    expect(composeMathQuestion('解释公式2', [
      { id: 'b', latex: 'x^2', displayMode: false, referenceNumber: 2 },
    ])).toContain('公式2：$x^2$');
  });
});
