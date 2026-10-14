import { describe, expect, it } from 'vitest';
import { readableVisualQuestion } from './visualQuestion';
describe('legacy visual question presentation', () => {
  it('retains complete problem and options without raw IR arrays', () => {
    const text = '请解题\n\n图片题干（识别文本，请校对）：\n求 $x^2=1$ 的解。\n\n实体：\n[{"id":"x","type":"variable"}]\n\n关系：\n[{"description":"平方关系"}]\n\n选项：\n["A. 1", "B. ±1"]\n\n用户标记：\n["圈选 B"]';
    const result = readableVisualQuestion(text);
    expect(result).toContain('求 $x^2=1$ 的解。');
    expect(result).toContain('A. 1\nB. ±1');
    expect(result).toContain('圈选 B');
    expect(result).not.toContain('variable');
    expect(result).not.toContain('["');
    expect(readableVisualQuestion(result)).toBe(result);
  });
  it('leaves ordinary prose and malformed structured content intact', () => {
    const text = '实体：\n这不是数组\n\n公式：\n[x, y';
    expect(readableVisualQuestion(text)).toBe(text);
  });
});
