import type { CandidateStructure } from '../../../types';

export function SourceStructure({ value, compact = false }: { value?: CandidateStructure | null; compact?: boolean }) {
  if (!value) return null;
  const rows = [
    ['位置', value.classification_path.filter(part => part !== 'default').join(' › ')],
    ['原题号', value.original_number],
    ['考点', value.authored_focus],
    ['试卷', [value.exam_year && !value.exam_source.includes(value.exam_year) && `${value.exam_year} 年`, value.exam_source].filter(Boolean).join(' · ')],
    ['目录号', value.catalog_number],
  ].filter(([, text]) => Boolean(text));
  if (!rows.length) return null;
  const content = <dl className="exercise-source-values">{rows.map(([label,text]) => <div key={label}><dt>{label}</dt><dd>{text}</dd></div>)}</dl>;
  return compact ? <details className="exercise-source-structure is-compact"><summary>题目出处</summary>{content}</details> : content;
}
