import type { ExerciseImportBatch } from '../../../types';

/** Keep source information readable; storage diagnostics stay in the receipt. */
export function BatchCandidateReceipts({ batch }: { batch: ExerciseImportBatch; bookQuery?: string }) {
  const numbers = (batch.candidate_receipts || []).map(r => r.projection.structure?.original_number).filter(Boolean);
  return <section className="exercise-import-receipts"><h3>导入来源</h3><p>{batch.source_label || '导入文件'}</p>{numbers.length > 0 && <p>题号：{numbers.join('、')}</p>}</section>;
}
