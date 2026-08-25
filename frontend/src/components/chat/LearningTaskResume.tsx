import { RotateCcw } from 'lucide-react';
import type { LearningTaskState } from '../../types';

export default function LearningTaskResume({
  task,
  onResume,
}: {
  task: LearningTaskState;
  onResume: (task: LearningTaskState) => void;
}) {
  const stage = String(task.artifacts?.resume_stage || '最近检查点');
  return (
    <div className="mt-3 border-l-2 border-accent/45 pl-3">
      <p className="text-xs leading-5 text-text-secondary">
        本次解答已暂停。原题、任务要求和已取得的证据仍保留（检查点：{stage}）。
      </p>
      <button
        type="button"
        onClick={() => onResume(task)}
        className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover"
      >
        <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
        继续本次解答
      </button>
    </div>
  );
}
