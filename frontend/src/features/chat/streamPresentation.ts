import type { ExecutionLifecycleState } from '../../utils/chatActivities';

/** Keep generated text separate from failure notices; never fabricate a final. */
export function streamFailure(partial: string, previous: string, reason: string) {
  return { content: partial || previous, streamError: reason || '连接中断，回答未完成' };
}

export function streamPresentation(lifecycle: ExecutionLifecycleState, previous: string) {
  if (lifecycle.terminalType === 'error') {
    return {
      content: lifecycle.hasOutput ? lifecycle.output : previous,
      streamError: lifecycle.errorMessage || '回答未完成',
    };
  }
  return { content: lifecycle.hasOutput ? lifecycle.output : previous, streamError: undefined };
}
