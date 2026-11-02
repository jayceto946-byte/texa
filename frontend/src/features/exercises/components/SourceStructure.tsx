import type { CandidateStructure } from '../../../types';

export function SourceStructure({ value }: { value?: CandidateStructure | null }) {
  if (!value || ![value.catalog_number, value.authored_focus, value.exam_source, value.original_number, value.exam_year, value.question_type].some(Boolean)) return null;
  return <div className="exercise-source-structure">
    {value.classification_path.some(p=>p!=='default') && <p>{value.classification_path.filter(p=>p!=='default').join(' › ')}</p>}
    {(value.catalog_number || value.authored_focus) && <p>{[value.catalog_number, value.authored_focus].filter(Boolean).join(' · ')}</p>}
    <p>{[value.exam_year && !value.exam_source.includes(value.exam_year) && `${value.exam_year} 年`, value.exam_source && `出处 ${value.exam_source}`, value.question_type, value.original_number && `原书题号 ${value.original_number}`].filter(Boolean).join(' · ')}</p>
  </div>;
}
