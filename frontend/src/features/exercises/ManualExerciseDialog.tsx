import { useCallback, useState } from 'react';
import Dialog from '../../components/ui/Dialog';
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
  return <Dialog open title="手动录入习题" onClose={closeDialog} className="note-dialog">
    <div className="note-toolbar"><h2>手动录入习题</h2><button className="app-ghost-button" disabled={busy} onClick={onClose}>取消</button></div>
    <fieldset className="note-fields" disabled={busy}><label>完整题干<textarea value={question} onChange={e => { setQuestion(e.target.value); setConfirmed(false); }} placeholder="条件、选项与公式（支持 LaTeX）"/></label><label>参考答案（可选）<textarea value={answer} onChange={e => setAnswer(e.target.value)}/></label><label className="note-checkbox"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>题干与关键条件已经核对完整</label></fieldset>
    {error && <p role="alert" className="note-warning">{error}</p>}<button className="app-primary-button" disabled={busy || !confirmed || !question.trim()} onClick={() => void save()}>{busy ? '正在保存…' : '保存到题库'}</button>
  </Dialog>;
}
