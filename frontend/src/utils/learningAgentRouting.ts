export type LearningAgentIntent = 'review' | 'progress' | 'practice' | 'textbook_example';

const REVIEW_PHRASES = [
  '今天复习什么',
  '今日复习',
  '复习计划',
  '到期错题',
  '错题到期',
  '哪些错题要复习',
  '薄弱知识点',
  '薄弱概念',
  '最近的薄弱点',
  '我的薄弱点',
];

const PROGRESS_PHRASES = [
  '最近进度',
  '学习进度',
  '最近学了',
  '学习记录',
  '本周学习',
  '这周学习',
  '最近学习情况',
];

const PRACTICE_PHRASES = [
  '安排练习',
  '开始练习',
  '按薄弱点练习',
  '练几道',
  '做几道',
  '抽几道',
  '组一套',
  '找几道练习',
  '找几道习题',
];

function includesAny(text: string, phrases: string[]) {
  return phrases.some((phrase) => text.includes(phrase));
}

export function classifyLearningAgentIntent(
  question: string,
  hasBook: boolean,
): LearningAgentIntent | null {
  if (!hasBook) return null;
  const normalized = question.replace(/\s+/g, '').toLowerCase();
  if (!normalized) return null;

  if (includesAny(normalized, PROGRESS_PHRASES)) return 'progress';
  if (includesAny(normalized, REVIEW_PHRASES)) return 'review';
  if (includesAny(normalized, PRACTICE_PHRASES)) return 'practice';
  if (
    normalized.includes('例题')
    && /(找|推荐|给我|来一道|来几道|有没有|列出).{0,16}例题/.test(normalized)
  ) {
    return 'textbook_example';
  }
  return null;
}

export function learningAgentStatus(intent: LearningAgentIntent): string {
  switch (intent) {
    case 'review':
      return '正在读取到期错题和薄弱概念…';
    case 'progress':
      return '正在汇总最近的学习记录…';
    case 'practice':
      return '正在筛选匹配的练习题…';
    case 'textbook_example':
      return '正在查找教材例题证据…';
  }
}

export function learningAgentFallbackStatus(): string {
  return '学习工具暂时未能完成，正在降级到普通回答…';
}
