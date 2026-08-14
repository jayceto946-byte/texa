import { describe, expect, it } from 'vitest';

import { prepareMathMarkdown } from './mathText';

describe('prepareMathMarkdown', () => {
  it('repairs inline math incorrectly split across Markdown paragraphs', () => {
    const value = '$ E(500,0)\\approx 37.005\\text{ mV}\n\nE(35,0)\\approx 2.110\\text{ mV}\n\nE(25,0)\\approx 1.496\\text{ mV} $';
    const output = prepareMathMarkdown(value);
    expect(output).toContain('$ E(500,0)\\approx 37.005\\text{ mV}$');
    expect(output).toContain('$E(35,0)\\approx 2.110\\text{ mV}$');
    expect(output).toContain('$E(25,0)\\approx 1.496\\text{ mV} $');
  });

  it('wraps bare temperature and formula-only LaTeX', () => {
    expect(prepareMathMarkdown('实际温度 t=500^\\circ\\text{C}，仪表显示多少？'))
      .toBe('实际温度 $t=500^\\circ\\text{C}$，仪表显示多少？');
    expect(prepareMathMarkdown('E_{\\text{disp}}=36.391\\text{ mV}'))
      .toBe('$E_{\\text{disp}}=36.391\\text{ mV}$');
  });
});
