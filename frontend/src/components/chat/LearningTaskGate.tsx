import { useRef, useState } from 'react';
import { FilePlus2, ListChecks } from 'lucide-react';
import type { LearningTaskState } from '../../types';

type Props = {
  task: LearningTaskState;
  onResume: (task: LearningTaskState, action: 'provide_input' | 'method_only', file?: File) => Promise<void> | void;
};

export default function LearningTaskGate({ task, onResume }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<'provide_input' | 'method_only' | ''>('');
  const [error, setError] = useState('');
  const missing = (task.required_inputs || []).filter((item) => item.blocking && item.status === 'missing');

  const run = async (action: 'provide_input' | 'method_only', file?: File) => {
    if (busy) return;
    setBusy(action);
    setError('');
    try {
      await onResume(task, action, file);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '恢复任务失败');
      setBusy('');
    }
  };

  return (
    <section className="mt-3 border-l-2 border-accent pl-3" aria-label="解答所需补充材料">
      <h3 className="text-sm font-semibold text-text-primary">精确解答需要补充材料</h3>
      <p className="mt-1 text-xs leading-5 text-text-secondary">原题和已完成解析已保留。补充后会继续当前任务，不会重新识别原图。</p>
      <ul className="mt-2 space-y-1.5 text-xs leading-5 text-text-secondary">
        {missing.map((item) => (
          <li key={`${item.type}-${item.name}`}>
            <span className="font-medium text-text-primary">{item.name}</span>
            {item.reason ? `：${item.reason}` : ''}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={Boolean(busy)}
          onClick={() => inputRef.current?.click()}
          className="app-primary-button disabled:opacity-50"
        >
          <FilePlus2 className="h-4 w-4" />
          {busy === 'provide_input' ? '正在解析补充材料' : '补充附表后精确计算'}
        </button>
        <button
          type="button"
          disabled={Boolean(busy)}
          onClick={() => void run('method_only')}
          className="app-secondary-button disabled:opacity-50"
        >
          <ListChecks className="h-4 w-4" />
          {busy === 'method_only' ? '正在继续原任务' : '暂不补充，只讲方法'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void run('provide_input', file);
            event.target.value = '';
          }}
        />
      </div>
      {error && <p className="mt-2 text-xs text-[var(--danger)]">{error}。原任务仍已保留，可以重试。</p>}
    </section>
  );
}
