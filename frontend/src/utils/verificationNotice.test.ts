import { describe, expect, it } from 'vitest';
import { readableVerificationNotice, separateVerificationNotice } from './verificationNotice';
describe('legacy deterministic verification notice', () => {
  it('humanizes only the exact notice and leaves formulas and unknown diagnostics intact', () => {
    const text = '$$formula(x)=x^2$$\n\n> 回答验收未通过：formula。本轮结果未标记为完整答案。';
    expect(readableVerificationNotice(text)).toContain('公式或推导关系未通过检查');
    expect(readableVerificationNotice(text)).toContain('$$formula(x)=x^2$$');
    const unknown = '> 回答验收未通过：custom_check。本轮结果未标记为完整答案。';
    expect(readableVerificationNotice(unknown)).toBe(unknown);
    expect(text).toContain('：formula。');
  });
});

describe('reading body and verification status', () => {
  const notice = '> 回答核对：部分公式或数值尚无确定性核验依据，请核对后使用。';
  it('keeps the actual answer and separates the system suffix for state presentation', () => {
    const content = '$$f(x)=x^2$$\n\n' + notice;
    const result = separateVerificationNotice(content);
    expect(result.body).toBe('$$f(x)=x^2$$');
    expect(result.notice).toContain('尚无确定性核验依据');
    expect(content).toContain(notice);
  });
  it('handles the old unverified suffix without dropping the status', () => {
    const result = separateVerificationNotice('正文\n\n> 回答核对：部分公式或数值尚无确定性核验依据，本轮结果未标记为完整答案。');
    expect(result.body).toBe('正文');
    expect(result.notice).not.toBe('');
  });
  it('preserves quoted explanations, code samples and explicit failed checks', () => {
    for (const content of [
      '解释\n\n' + notice + '\n\n后续解释',
      '```markdown\n\n' + notice,
      '~~~markdown\n\n' + notice + '\n~~~',
      '正文\n\n> 回答验收未通过：数值未通过检查。这些结论仍需核对。',
      '正文\n\n> 回答核对：另一种未知警告。',
    ]) {
      expect(separateVerificationNotice(content)).toEqual({body: content, notice: ''});
    }
  });
});
