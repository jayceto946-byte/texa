import type { CandidateStructure } from '../../../types';

export function SourceStructure({ value, compact = false }: { value?: CandidateStructure | null; compact?: boolean }) {
  if (!value || ![value.catalog_number, value.authored_focus, value.exam_source, value.original_number, value.exam_year, value.question_type].some(Boolean)) return null;
  const full = <div className="exercise-source-structure">
    {value.classification_path.some(p=>p!=='default') && <p>{value.classification_path.filter(p=>p!=='default').join(' › ')}</p>}
    {(value.catalog_number || value.authored_focus) && <p>{[value.catalog_number, value.authored_focus && `考点 ${value.authored_focus}`].filter(Boolean).join(' · ')}</p>}
    <p>{[value.exam_year && !value.exam_source.includes(value.exam_year) && `${value.exam_year} 年`, value.exam_source && `出处 ${value.exam_source}`, value.question_type, value.original_number && `原书题号 ${value.original_number}`].filter(Boolean).join(' · ')}</p>
  </div>;
  if (!compact) return full;
  return <div className="exercise-source-structure is-compact">
    {(value.original_number || value.authored_focus) && <p>{[value.original_number && `原书题号 ${value.original_number}`, value.authored_focus && `考点 ${value.authored_focus}`].filter(Boolean).join(' · ')}</p>}
    <details><summary>题目来源</summary>{full}</details>
  </div>;
}
