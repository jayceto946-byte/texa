import { useState } from 'react';
import { ChevronRight, Trash2 } from 'lucide-react';
import { SimpleMarkdown } from '../../../components/chat/MarkdownRenderer';
import { exercisePreview } from '../exercisePreview';
import { exerciseSourceCategory, exerciseSourceLabels } from '../exerciseSource';
import { exerciseStatusText } from './ExercisePresentation';
import type { ExerciseRecord } from '../../../types';

export function ExerciseBankList({ records, visibleRecords, textbookName, textbookLabel, disabled, onOpen, onDelete }: {
  records: ExerciseRecord[]; visibleRecords: ExerciseRecord[]; textbookName: string; textbookLabel: string;
  disabled: boolean; onOpen: (id: string) => void; onDelete: (records: ExerciseRecord[]) => void;
}) {
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const selected = records.filter(record => selection.has(record.id));
  const allSelected = records.length > 0 && selected.length === records.length;
  const toggle = (id: string) => setSelection(previous => {
    const next = new Set(previous);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  return <>
    {records.length > 0 && <div className="exercise-bank-management">
      <label><input type="checkbox" checked={allSelected} ref={input => { if (input) input.indeterminate = selected.length > 0 && !allSelected; }} disabled={disabled} onChange={() => setSelection(allSelected ? new Set() : new Set(records.map(record => record.id)))} />全选本次加载的 {records.length} 题</label>
      <div><span role="status">已选 {selected.length} 题</span>{selected.length > 0 && <button className="app-ghost-button" disabled={disabled} onClick={() => setSelection(new Set())}>取消选择</button>}<button className="app-secondary-button" disabled={disabled || !selected.length} onClick={() => onDelete(selected)}><Trash2 size={14} />删除选中</button></div>
    </div>}
    {visibleRecords.map(record => {
      const category = exerciseSourceCategory(record, textbookName);
      const preview = exercisePreview(record.question_text || record.source, 160, 160);
      return <article key={record.id} className={`exercise-bank-row${selection.has(record.id) ? ' is-selected' : ''}`}>
        <input className="exercise-bank-check" type="checkbox" aria-label={`选择题目：${exercisePreview(record.question_text, 36)}`} checked={selection.has(record.id)} disabled={disabled} onChange={() => toggle(record.id)} />
        <button onClick={() => onOpen(record.id)} className="exercise-bank-open">
          <div className="exercise-bank-content">
            <SimpleMarkdown content={preview} className="exercise-bank-question" />
            <div className="exercise-bank-source"><span>{category === 'textbook_example' ? '来自教材' : '题目来源'}</span><strong>{category === 'textbook_example' ? textbookLabel || textbookName : record.source || exerciseSourceLabels[category]}</strong>{record.chapter && <span>{record.chapter}</span>}</div>
            {(record.source_structure?.exam_source || record.source_structure?.authored_focus) && <div className="exercise-metadata-tags">
              {record.source_structure?.exam_source && <span title={record.source_structure.exam_source}>来源 · {record.source_structure.exam_source}</span>}
              {record.source_structure?.authored_focus && <span title={record.source_structure.authored_focus}>考点 · {record.source_structure.authored_focus}</span>}
            </div>}
            <div className="exercise-bank-facts"><span className="exercise-source-kind">{exerciseSourceLabels[category] || '习题'}</span>{record.question_type && record.question_type !== '未确定' && <span>{record.question_type}</span>}<span>练习 {record.practice_count || 0} 次</span></div>
          </div>
          <span className="exercise-bank-status">{exerciseStatusText[record.status] || record.status}</span><ChevronRight className="exercise-bank-chevron" size={14} />
        </button>
        <button type="button" className="exercise-bank-delete" disabled={disabled} title="删除题目" aria-label={`删除题目：${exercisePreview(record.question_text, 36)}`} onClick={() => onDelete([record])}><Trash2 size={15} /></button>
      </article>;
    })}
  </>;
}
