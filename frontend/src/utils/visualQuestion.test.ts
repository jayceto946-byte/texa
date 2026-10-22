import { describe, expect, it } from 'vitest';
import { readableVisualQuestion, visualUserQuestion } from './visualQuestion';
import { prepareMathMarkdown } from './mathText';
describe('legacy visual question presentation', () => {
  it('keeps the user request in a photo bubble without OCR or losing the question', () => {
    const request = '为什么36题不能直接替换，37却可以？';
    const content = request + '\n\n图片题干（识别文本，请校对）：\n' + JSON.stringify({ schema_version: 'visual-problem-ir/v2', problem_text: 'internal OCR' });
    expect(visualUserQuestion(content)).toBe(request);
    expect(visualUserQuestion(content, request)).toBe(request);
    expect(visualUserQuestion('{"schema_version":"visual-problem-ir/v2","problem_text":"internal"}')).toBe('请解答图片中的问题。');
    expect(visualUserQuestion('请解答这道题。')).toBe('请解答这道题。');
  });
  it('retains complete problem and options without raw IR arrays', () => {
    const text = '请解题\n\n图片题干（识别文本，请校对）：\n求 $x^2=1$ 的解。\n\n实体：\n[{"id":"x","type":"variable"}]\n\n关系：\n[{"description":"平方关系"}]\n\n选项：\n["A. 1", "B. ±1"]\n\n用户标记：\n["圈选 B"]';
    const result = readableVisualQuestion(text);
    expect(result).toContain('求 $x^2=1$ 的解。');
    expect(result).toContain('A. 1\nB. ±1');
    expect(result).not.toContain('圈选 B');
    expect(result).not.toContain('平方关系');
    expect(result).not.toContain('variable');
    expect(result).not.toContain('["');
    expect(readableVisualQuestion(result)).toBe(result);
  });
  it('leaves ordinary prose and malformed structured content intact', () => {
    const text = '实体：\n这不是数组\n\n公式：\n[x, y';
    expect(readableVisualQuestion(text)).toBe(text);
  });
});


describe('visual IR question projection', () => {
  const stem = String.raw`[37]（2016年数学一）
\(\lim_{x\to0}\frac{\int_0^x t\ln(1+\sin t)\,dt}{1-\cos x^2}=\underline{\hspace{3cm}}\)`;
  const ir = { schema_version: 'visual-problem-ir/v2', problem_text: stem, visual_type: 'text_only',
    visual_summary: '布局说明', entities: [{ properties: { position: '题干上方左侧' } }],
    relations: [{ description: '积分是分子' }], annotations: ['题号在左上角'],
    formulas: [String.raw`\frac{a}{b}`], options: ['A. 0', 'B. 1'], user_marks: ['圈选 B'] };
  it('shows only the actual stem and options from persisted JSON', () => {
    const text = readableVisualQuestion(JSON.stringify(ir));
    expect(text).toBe(stem + '\n\nA. 0\nB. 1');
    expect(readableVisualQuestion(text)).toBe(text);
    expect(text).not.toMatch(/schema_version|entities|position|properties|visual_summary/);
    const markdown = prepareMathMarkdown(text);
    expect(markdown).toContain(String.raw`\lim_{x\to0}\frac{\int_0^x`);
    expect(markdown).not.toContain('MATH_PROTECTED');
  });
  it('unwraps the old fallback nested under problem_text', () => {
    expect(readableVisualQuestion(JSON.stringify({ ...ir, problem_text: JSON.stringify(ir) }))).toBe(stem + '\n\nA. 0\nB. 1');
  });
  it('repairs raw OCR LaTeX escaping without eating frac, theta or newlines', () => {
    const raw = String.raw`{"schema_version":"visual-problem-ir/v2","problem_text":"题目\n\(\frac{1}{2}+\theta+\beta+\nu+\rho\)","visual_type":"text_only","entities":[]}`;
    expect(readableVisualQuestion(raw)).toBe('题目\n' + String.raw`\(\frac{1}{2}+\theta+\beta+\nu+\rho\)`);
  });
  it('asks for correction instead of displaying broken JSON or inferring the stem', () => {
    expect(readableVisualQuestion('{"schema_version":"visual-problem-ir/v2","problem_text":"broken')).toBe('题干识别结果需要重新校对，请对照原图补全。');
    expect(readableVisualQuestion('{"schema_version":"visual-problem-ir/v2","problem_text":"broken', '')).toBe('');
  });
  it('leaves ordinary questions, legitimate JSON and LaTeX unchanged', () => {
    for (const text of [String.raw`求 $\frac{a}{b}$`, '{"name":"问题正文"}', '公式：\n[x, y']) expect(readableVisualQuestion(text)).toBe(text);
  });
});
