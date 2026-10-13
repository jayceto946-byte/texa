import type { ChatActivity } from '../types';

export function answerVerificationLabel(verification: Record<string, unknown> | undefined, activities: ChatActivity[], taskStatus?: string): string {
  const status = verification?.status || [...activities].reverse().find(item => typeof item.meta?.verification_status === 'string')?.meta?.verification_status;
  if (status === 'passed' && taskStatus !== 'degraded') return '处理完成';
  if (status === 'failed') return '部分结论未通过检查';
  if (status === 'unverified') return '部分内容尚未验证，需要核对';
  if (status === 'degraded' || taskStatus === 'degraded') return '回答已生成，部分内容需要核对';
  if (status === 'not_run' || status === 'pending' || status === 'unknown') return '回答已生成，尚未完成检查';
  return '处理完成';
}
