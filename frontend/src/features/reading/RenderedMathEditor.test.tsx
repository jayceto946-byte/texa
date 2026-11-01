import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RenderedMathEditor } from './RenderedMathEditor';
import { replaceSourceText, replaceSourceFormula } from './sourceTextEdit';

describe('rendered source editing', () => {
  it('shows inline and display formulas as rendered math with source ranges', () => {
    const source = '长度 $L_1=100\\mathrm{mm}$。\n\n$$\n\\frac{2}{100}=0.02\n$$';
    const html = renderToStaticMarkup(<RenderedMathEditor label="题干" value={source} onChange={() => {}} />);
    expect((html.match(/class="rendered-edit-formula"/g) || []).length).toBe(2);
    expect(html).toContain('class="katex"');
    expect(html).toContain('data-start="3"');
    expect(html).not.toContain('<textarea');
  });
  it('preserves formulas and Markdown when changing a text span', () => {
    const source = '| 数值 | 说明 |\n| --- | --- |\n| $x$ | 测量值 |';
    const start = source.indexOf('测量值');
    expect(replaceSourceText(source, start, start + 3, '修正值')).toBe(source.replace('测量值', '修正值'));
    const html = renderToStaticMarkup(<RenderedMathEditor label="解析" value={source} onChange={() => {}} />);
    expect(html).toContain('<table>');
    expect(html).toContain('contentEditable="plaintext-only"');
  });
  it('renders a newly inserted formula after an existing answer as display math', () => {
    const original = '答案为';
    const source = replaceSourceFormula(original, original.length, original.length, 'x^2+1', true);
    const html = renderToStaticMarkup(<RenderedMathEditor label="答案" value={source} onChange={() => {}} />);
    expect(html).toContain('class="katex-display"');
    expect(html).toContain('class="rendered-edit-formula"');
  });
});
