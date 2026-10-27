import type { CandidateStructure } from '../../../types';

export function SourceStructure({ value }: { value?: CandidateStructure | null }) {
  if (!value || ![value.catalog_number, value.authored_focus, value.exam_source].some(Boolean)) return null;
  return <div className="exercise-source-structure">
    {value.classification_path.length > 0 && <p>{value.classification_path.join(' › ')}</p>}
    <p>{[value.catalog_number, value.authored_focus].filter(Boolean).join(' · ')}</p>
    <p>{[value.exam_source && `出处 ${value.exam_source}`, value.original_number && `原卷题号 ${value.original_number}`].filter(Boolean).join(' · ')}</p>
  </div>;
}
