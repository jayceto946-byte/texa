import { useState } from 'react';
import { get } from '../../../api/client';
import type { ExerciseImportBatch } from '../../../types';
import { candidateHash } from '../hooks/candidateContract';
import { SourceStructure } from './SourceStructure';

/** Receipts describe the import-time version; they never certify later edits. */
export function BatchCandidateReceipts({ batch, bookQuery }: { batch: ExerciseImportBatch; bookQuery: string }) {
  const [versions, setVersions] = useState<Record<string, string>>({});
  const check = async () => {
    const receipts = batch.candidate_receipts || [];
    let cursor = 0;
    const entries: Array<[string, string]> = [];
    await Promise.all(Array.from({ length: Math.min(4, receipts.length) }, async () => {
      while (cursor < receipts.length) {
        const receipt = receipts[cursor++];
        try {
          const res = await get(`/exercises/${encodeURIComponent(receipt.exercise_id)}${bookQuery}`);
          entries.push([receipt.exercise_id, res?.data && await candidateHash(res.data, false) === receipt.body_hash ? '正文与导入时相同' : '正文已更改或缺失，仅为历史导入事实']);
        } catch { entries.push([receipt.exercise_id, '正文不可读取，仅为历史导入事实']); }
      }
    }));
    setVersions(Object.fromEntries(entries));
  };
  return <details className="exercise-import-receipts"><summary>批次 {batch.id} · 来源与导入时校对信息</summary>{batch.candidate_receipts?.length ? <><button className="app-secondary-button" onClick={() => void check()}>核对正文版本</button>{batch.candidate_receipts.map(receipt => <details key={receipt.exercise_id}><summary>{receipt.origin_id} → {receipt.exercise_id} · 导入时：{receipt.review_kind === 'user_confirmed' ? '用户确认' : '系统提案'}</summary><SourceStructure value={receipt.projection.structure} /><p>{versions[receipt.exercise_id] || '尚未核对当前正文；此处记录导入时状态。'}</p><p>来源版本 {receipt.projection.canonical_hash} · {receipt.projection.method}</p><p>来源单元 {receipt.projection.unit_ids.join('、')}</p>{Object.entries(receipt.projection.parts).map(([role, spans]) => spans.length ? <p key={role}>{({ question: '题干', answer: '答案', explanation: '解析', context: '旁文', unassigned: '未精确对齐的来源依据' } as Record<string,string>)[role]}：{spans.map(span => `${span.block_id} [${span.start}, ${span.end ?? '全文末尾'})`).join('；')}</p> : null)}<p>来源正文按上述版本回查；文件来源快照独立保留，版本缺失时请重新分析。</p></details>)}</> : <p>未新增题目校对回执。</p>}{batch.skipped_candidate_receipts?.map(receipt => <details key={`skip-${receipt.origin_id}`}><summary>重复题来源关联 · {receipt.origin_id} → {receipt.exercise_id}</summary><SourceStructure value={receipt.projection.structure} /><p>保留本次来源与考点；旧题正文及确认状态保持原样。</p><p>来源版本 {receipt.projection.canonical_hash} · 单元 {receipt.projection.unit_ids.join('、')}</p></details>)}</details>;
}
