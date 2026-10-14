import { describe, expect, it } from 'vitest';
import { goalErrorText, goalEventText } from './runtimePresentation';
describe('goal runtime presentation', () => {
  it('describes a resumed run and verified/degraded finals without raw lifecycle identifiers', () => {
    const event = {type:'state_transition' as const, phase:'run', status:'started' as const, payload:{lifecycle:'run.resumed'}};
    expect(goalEventText(event)).toBe('继续原任务');
    expect(goalEventText({...event,type:'final',payload:{verification_status:'passed'}})).toBe('本次任务已完成');
    expect(goalEventText({...event,type:'final',payload:{verification_status:'unverified'}})).toContain('需要核对');
    expect(goalEventText({...event,phase:'internal',payload:{}})).not.toContain('internal');
  });
  it('keeps actionable Chinese guidance and replaces English exceptions', () => {
    expect(goalErrorText(new Error('task cannot resume at this revision'))).toContain('刷新任务状态');
    expect(goalErrorText(new Error('目标已暂停，请刷新后重试'))).toBe('目标已暂停，请刷新后重试');
  });
});
