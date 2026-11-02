import { useCallback, useState } from 'react';
import Dialog from '../../components/ui/Dialog';
import { MathContentField } from '../reading/RenderedMathEditor';
import { StatusBanner } from '../../components/ui/AsyncState';
import { post } from '../../api/client';

export default function ManualExerciseDialog({ scope, subject, onClose, onSaved }: { scope: string; subject: string; onClose: () => void; onSaved: () => void }) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const closeDialog = useCallback(() => { if (!busy) onClose(); }, [busy, onClose]);
  const save = async () => {
    if (busy || !confirmed || !question.trim()) return;
    setBusy(true); setError('');
    try {
      const result = await post(`/exercises/add?book_name=${encodeURIComponent(scope)}`, { question_text: question, answer, subject, source: '手动录入', origin_type: 'manual' });
      if (!result.success) throw new Error(result.message || '保存习题失败');
      onSaved(); onClose();
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存失败'); }
    finally { setBusy(false); }
  };
  return <Dialog open title="手动录入习题" onClose={closeDialog} className="exercise-manual-dialog">
    <div className="exercise-row"><h2>手动录入习题</h2><button className="app-ghost-button" disabled={busy} onClick={onClose}>取消</button></div>
    <fieldset className="exercise-manual-fields" disabled={busy}>
      <MathContentField label="完整题干" value={question} disabled={busy} onChange={value => { setQuestion(value); setConfirmed(false); }} />
      <MathContentField label="参考答案（可选）" value={answer} disabled={busy} onChange={setAnswer} />
      <label className="exercise-manual-confirm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />题干与关键条件已经核对完整</label>
    </fieldset>
    {error && <StatusBanner kind="error" title={error} description="输入内容已保留，可以重试保存。" />}<button className="app-primary-button" disabled={busy || !confirmed || !question.trim()} onClick={() => void save()}>{busy ? '正在保存…' : '保存到题库'}</button>
  </Dialog>;
}
