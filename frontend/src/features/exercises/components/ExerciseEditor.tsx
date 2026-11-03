import { useState } from 'react';
import Dialog from '../../../components/ui/Dialog';
import { post } from '../../../api/client';
import type { ExerciseRecord } from '../../../types';
import { MathContentField } from '../../reading/RenderedMathEditor';
import { ExerciseAttachments } from './ExerciseAttachments';

export function ExerciseEditor({ record, bookQuery, onSaved, onClose }: { record: ExerciseRecord; bookQuery: string; onSaved: (record: ExerciseRecord) => void; onClose: () => void }) {
  const [body, setBody] = useState({ question_text: record.question_text, answer: record.answer, explanation: record.explanation });
  const [removed, setRemoved] = useState<string[]>([]);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const bookName = new URLSearchParams(bookQuery).get('book_name') || 'default';
  const save = async () => {
    setBusy(true); setError('');
    try {
      const result = await post('/exercises/edit' + bookQuery, { id: record.id, ...body, removed_asset_ids: removed, reviewed });
      if (!result?.success) throw Error(result?.message || '保存失败，请重试');
      onSaved(result.data); onClose();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  return <Dialog open title="编辑题目" onClose={() => { if (!busy) onClose(); }} className="exercise-edit-dialog">
    <h2>编辑题目</h2>
    <fieldset disabled={busy}>
      {([['question_text', '题干'], ['answer', '参考答案'], ['explanation', '解析']] as const).map(([key, label]) => <MathContentField key={key} label={label} value={body[key]} disabled={busy} onChange={value => setBody(current => ({ ...current, [key]: value }))} />)}
      {record.source_attachments?.map(asset => <section className="exercise-figure-item" key={`${asset.asset_id}:${asset.role}`}>
        {!removed.includes(asset.asset_id) && <ExerciseAttachments showLabels={false} record={{ ...record, source_attachments: [asset] }} bookName={bookName} roles={[asset.role]} />}
        <div><span>{asset.label || '配图'}{removed.includes(asset.asset_id) ? ' · 已移除' : ''}</span><button type="button" className="app-secondary-button" onClick={() => setRemoved(current => current.includes(asset.asset_id) ? current.filter(id => id !== asset.asset_id) : [...current, asset.asset_id])}>{removed.includes(asset.asset_id) ? '恢复图片' : '移除图片'}</button></div>
      </section>)}
      <label className="exercise-edit-reviewed"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />标记本题已核对</label>
    </fieldset>
    {error && <p role="alert" className="exercise-warning">{error}</p>}
    <footer><button className="app-secondary-button" disabled={busy} onClick={onClose}>取消</button><button className="app-primary-button" disabled={busy || !body.question_text.trim()} onClick={() => void save()}>{busy ? '正在保存…' : '保存修改'}</button></footer>
  </Dialog>;
}
