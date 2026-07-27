import { describe, expect, it } from 'vitest';

import { composeMathQuestion } from './composeMathQuestion';

describe('composeMathQuestion', () => {
  it('keeps ordinary text and appends visual math blocks as valid markdown', () => {
    expect(composeMathQuestion('请计算', [
      { id: 'a', latex: '\\frac{1}{2}', displayMode: false },
      { id: 'b', latex: '\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}', displayMode: true },
    ])).toBe('请计算\n\n公式 1：$\\frac{1}{2}$\n\n公式 2：\n\n$$\n\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}\n$$');
  });

  it('allows sending a formula without ordinary text', () => {
    expect(composeMathQuestion('', [{ id: 'a', latex: 'x^2', displayMode: false }])).toBe('公式 1：$x^2$');
  });

  it('skips empty expressions', () => {
    expect(composeMathQuestion('问题', [{ id: 'a', latex: '  ', displayMode: true }])).toBe('问题');
  });
});
