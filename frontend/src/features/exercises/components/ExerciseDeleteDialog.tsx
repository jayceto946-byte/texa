import Dialog from '../../../components/ui/Dialog';
import { SimpleMarkdown } from '../../../components/chat/MarkdownRenderer';
import { exercisePreview } from '../exercisePreview';
import type { ExerciseRecord } from '../../../types';

export function ExerciseDeleteDialog({ records, deleting, error, onCancel, onConfirm }: {
  records: ExerciseRecord[]; deleting: boolean; error: string;
  onCancel: () => void; onConfirm: () => void;
}) {
  return <Dialog open={records.length > 0} title="删除题目" onClose={onCancel} className="exercise-delete-dialog">
    <h2>{records.length === 1 ? '删除这道题目？' : `删除选中的 ${records.length} 道题目？`}</h2>
    <p>题目将从当前题库永久删除，无法撤销。已保存的错题和笔记不受影响。</p>
    <ul className="exercise-delete-previews">{records.slice(0, 3).map(record => <li key={record.id}><SimpleMarkdown content={exercisePreview(record.question_text, 90, 60)} /></li>)}</ul>
    {records.length > 3 && <p>以及另外 {records.length - 3} 道题目。</p>}
    {error && <p role="alert" className="exercise-delete-error">{error}</p>}
    <footer><button className="app-secondary-button" disabled={deleting} onClick={onCancel}>取消</button><button className="app-secondary-button exercise-delete-confirm" disabled={deleting} onClick={onConfirm}>{deleting ? '正在删除…' : `确认删除${records.length > 1 ? ` ${records.length} 道` : ''}`}</button></footer>
  </Dialog>;
}
