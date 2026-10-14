import type { ExecutionEvent } from '../../types';

const phases: Record<string, string> = {
  run: '处理学习任务', model: '整理学习内容', tool: '使用学习工具',
  planning: '整理问题', retrieval: '查找教材', evidence: '准备教材依据', generation: '生成回答',
};
export function goalEventText(event: Pick<ExecutionEvent, 'type' | 'phase' | 'status' | 'payload'>): string {
  const lifecycle = event.payload?.lifecycle;
  if (lifecycle === 'run.resumed') return '继续原任务';
  if (lifecycle === 'run.created') return '开始学习任务';
  if (event.type === 'final') return event.payload?.verification_status === 'passed' ? '本次任务已完成' : '回答已生成，部分内容需要核对';
  if (event.type === 'error' || event.status === 'failed') return '本次处理未完成，请检查状态后重试';
  if (event.payload?.task_status_after === 'interrupted') return '已暂停，原任务和已取得的结果保留';
  if (event.payload?.task_status_after === 'waiting_for_confirmation') return '等待你确认学习记录操作';
  if (event.payload?.task_status_after === 'waiting_for_input') return '等待补充必要信息';
  return `${phases[event.phase] || '处理学习任务'} · ${{started: '已开始', running: '进行中', completed: '已完成', skipped: '已跳过', cancelled: '已停止'}[event.status] || '状态已更新'}`;
}

export function goalErrorText(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : '';
  // Keep known Chinese service guidance. Technical identifiers and English
  // exceptions remain in the API/runtime diagnostic records.
  return /[\u4e00-\u9fff]/.test(message) && !/Runtime|Traceback|Error:|Exception|request_key|task cannot|HTTP\s*\d/i.test(message)
    ? message : '操作未完成。请刷新任务状态后重试；如仍失败，请检查模型连接或查看诊断日志。';
}
