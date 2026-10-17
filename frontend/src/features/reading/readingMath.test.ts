import { describe, expect, it } from 'vitest';
import { readingMathMarkdown } from './readingMath';
describe('reading math display boundaries', () => {
  it('preserves inline math while giving display equations block boundaries', () => { expect(readingMathMarkdown('$x$ 与 $$x^2$$')).toBe('$x$ 与 \n\n$$\nx^2\n$$\n\n'); });
  it('never changes literal code', () => { expect(readingMathMarkdown('```tex\n$$x$$\n``` and `$$y$$`')).toBe('```tex\n$$x$$\n``` and `$$y$$`'); });
  it('keeps matrices and model headings intact', () => { const text='## 模型标题\n\n$$\n\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}\n$$';expect(readingMathMarkdown(text)).toContain('\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}');expect(readingMathMarkdown(text)).toContain('## 模型标题'); });
});
