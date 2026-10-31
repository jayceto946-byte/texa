import Selector from '../../../components/ui/Selector';
import { useRef, useState } from 'react';
import type { CandidateSourceBlock } from '../../../types';

export function SourceRoleAssignment({ block, disabled, onAssign }: { block: CandidateSourceBlock; disabled: boolean; onAssign: (offset: number, role: 'question' | 'answer' | 'explanation' | 'context') => void }) {
  const text = useRef<HTMLTextAreaElement>(null);
  const [role, setRole] = useState<'question' | 'answer' | 'explanation' | 'context'>('explanation');
  return <details className="exercise-source-assignment"><summary>调整本块题干与解答分界</summary>
    <p>将光标放在分界处，再分配光标后的本块文字。原始文字保留，修改后需重新确认。</p>
    <textarea ref={text} aria-label={`来源文字 ${block.block_id}`} readOnly value={block.text} rows={5} disabled={disabled} />
    <div className="exercise-row"><label>分配到<Selector ariaLabel={`来源角色 ${block.block_id}`} value={role} onChange={value => setRole(value as typeof role)} options={[{ value: "question", label: "题干" }, { value: "answer", label: "答案" }, { value: "explanation", label: "解析" }, { value: "context", label: "旁文" }]} disabled={disabled} compact/></label>
      <button className="app-secondary-button" disabled={disabled || !block.text} onClick={() => onAssign(text.current?.selectionStart ?? 0, role)}>分配光标后的本块文字</button></div>
  </details>;
}
