import { describe, expect, it } from 'vitest';
import { exercisePreview } from './exercisePreview';
describe('exercise list previews', () => {
  it('keeps short inline LaTeX and mixed Chinese punctuation', () => {
    expect(exercisePreview('设函数 $f(x)=\\sin x$。求 $f(0)$。')).toBe('设函数 $f(x)=\\sin x$。求 $f(0)$。');
  });
  it('keeps a short display formula as one inline token', () => {
    expect(exercisePreview('求值 $$x^2+1$$。')).toBe('求值 $x^2+1$。');
  });
  it('uses an explicit placeholder for long or multiline formulas', () => {
    expect(exercisePreview(`设 $${'a+'.repeat(30)}b$，求值。`)).toBe('设 〔公式〕，求值。');
    expect(exercisePreview('计算 $$\nx+y\n=z\n$$。')).toBe('计算 〔公式〕。');
  });
  it('does not leave half a formula at the length boundary', () => {
    expect(exercisePreview('计算 $x^2+y^2$ 后求导。', 8)).toBe('计算…');
  });
  it('supports several formulas and ordinary questions', () => {
    expect(exercisePreview('$x$、$y$ 与 $z$')).toBe('$x$、$y$ 与 $z$');
    expect(exercisePreview('\n判断命题是否成立。\n第二行')).toBe('判断命题是否成立。');
    expect(exercisePreview('')).toBe('题干待补全');
  });
});
