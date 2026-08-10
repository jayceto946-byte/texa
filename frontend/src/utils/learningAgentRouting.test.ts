import { describe, expect, it } from 'vitest';
import { classifyLearningAgentIntent, learningAgentFallbackStatus, learningAgentStatus } from './learningAgentRouting';

describe('classifyLearningAgentIntent', () => {
  it.each([
    ['我今天复习什么？', 'review'],
    ['看看有哪些到期错题', 'review'],
    ['总结一下我最近的学习进度', 'progress'],
    ['给我安排练习，做几道极限题', 'practice'],
    ['找一道教材里的极限例题', 'textbook_example'],
  ] as const)('routes explicit learning task: %s', (question, expected) => {
    expect(classifyLearningAgentIntent(question, true)).toBe(expected);
  });

  it.each([
    '解释一下数列极限',
    '这道题怎么做？',
    '继续讲第二步',
    '证明拉格朗日中值定理',
    '把这道题加入错题本',
    '讲解这道教材例题',
  ])('keeps ordinary QA on the RAG path: %s', (question) => {
    expect(classifyLearningAgentIntent(question, true)).toBeNull();
  });

  it('does not start textbook-scoped tools without a selected book', () => {
    expect(classifyLearningAgentIntent('我今天复习什么？', false)).toBeNull();
  });
});

describe('learningAgentStatus', () => {
  it('provides a visible status for every routed intent', () => {
    expect(learningAgentStatus('review')).toContain('到期错题');
    expect(learningAgentStatus('progress')).toContain('学习记录');
    expect(learningAgentStatus('practice')).toContain('练习题');
    expect(learningAgentStatus('textbook_example')).toContain('教材例题');
  });

  it('makes the ordinary-answer fallback visible', () => {
    expect(learningAgentFallbackStatus()).toContain('降级到普通回答');
  });
});
