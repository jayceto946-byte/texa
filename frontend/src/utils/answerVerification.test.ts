import { expect, it } from 'vitest';
import { answerVerificationLabel } from './answerVerification';
it('distinguishes failed, unsupported, missing verification and a passed release gate', () => {
  expect(answerVerificationLabel({status:'failed'},[])).toContain('未通过');
  expect(answerVerificationLabel({status:'unverified'},[])).toContain('尚未验证');
  expect(answerVerificationLabel({status:'unknown'},[])).toContain('尚未完成');
  expect(answerVerificationLabel({status:'passed'},[])).toBe('处理完成');
  expect(answerVerificationLabel({status:'passed'},[],'degraded')).toContain('需要核对');
  expect(answerVerificationLabel(undefined,[{id:'final',kind:'system',label:'done',status:'completed',meta:{verification_status:'unverified'}}])).toContain('需要核对');
});
