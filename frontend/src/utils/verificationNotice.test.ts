import { describe, expect, it } from 'vitest';
import { readableVerificationNotice } from './verificationNotice';
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
