import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react';
import { MarkdownMessage } from '../../components/chat/MarkdownMessage';
import MathFieldEditor from '../math-input/MathFieldEditor';
import type { NoteBlock, NoteContent } from './types';
export function blockMarkdown(block: NoteBlock): string {
    const d = block.data;
    if (block.type === 'heading')
        return `${'#'.repeat(d.level || 2)} ${d.text}`;
    if (block.type === 'equation')
        return `$$\n${d.latex}\n$$\n${d.annotation || ''}`;
    if (block.type === 'list')
        return (d.items || []).map((item, i) => `${d.ordered ? `${i + 1}.` : '-'} ${item}`).join('\n');
    return d.markdown || '';
}
export function NoteBlocks({ blocks }: {
    blocks: NoteBlock[];
}) {
    return <div className="note-reading">{blocks.map(block => <section key={block.block_id} id={block.block_id} className={`note-block note-${block.type}`}>
    <MarkdownMessage disableRemoteMedia content={blockMarkdown(block)}/>

  </section>)}</div>;
}
export function BlockEditor({ content, onChange }: {
    content: NoteContent;
    onChange: (content: NoteContent) => void;
}) {
    const update = (index: number, patch: Partial<NoteBlock>) => onChange({ ...content, blocks: content.blocks.map((b, i) => i === index ? { ...b, ...patch } : b) });
    const move = (index: number, delta: number) => {
        const blocks = [...content.blocks];
        const target = index + delta;
        [blocks[index], blocks[target]] = [blocks[target], blocks[index]];
        onChange({ ...content, blocks });
    };
    return <div className="note-editor">{content.blocks.map((block, i) => <section key={block.block_id} className="note-edit-block" id={block.block_id}>
    <div className="note-toolbar"><span>{({ heading: '标题', paragraph: '段落', equation: '公式', list: '列表', callout: '提示' })[block.type]} · {i + 1}</span><div className="note-actions">
      <button className="app-icon-button" aria-label={`上移第 ${i + 1} 块`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={16}/></button>
      <button className="app-icon-button" aria-label={`下移第 ${i + 1} 块`} disabled={i === content.blocks.length - 1} onClick={() => move(i, 1)}><ArrowDown size={16}/></button>
      <button className="app-icon-button" aria-label={`删除第 ${i + 1} 块`} disabled={content.blocks.length === 1} onClick={() => onChange({ ...content, blocks: content.blocks.filter((_, n) => n !== i) })}><Trash2 size={16}/></button>
    </div></div>
    {block.type === 'equation' ? <><MathFieldEditor value={block.data.latex || ''} onChange={latex => update(i, { data: { ...block.data, latex } })} ariaLabel={`第 ${i + 1} 块公式`}/><label>公式说明<input value={block.data.annotation || ''} onChange={e => update(i, { data: { ...block.data, annotation: e.target.value } })}/></label></> : <label className="note-block-input">{block.type === 'heading' ? '标题文字' : 'Markdown 正文'}<textarea aria-label={`第 ${i + 1} 块正文`} value={block.type === 'heading' ? block.data.text || '' : block.type === 'list' ? (block.data.items || []).join('\n') : block.data.markdown || ''} onChange={e => update(i, { data: { ...block.data, ...(block.type === 'heading' ? { text: e.target.value } : block.type === 'list' ? { items: e.target.value.split('\n') } : { markdown: e.target.value }) } })}/></label>}
  </section>)}<div className="note-actions">{(['paragraph', 'heading', 'equation', 'list', 'callout'] as const).map(type => <button className="app-secondary-button" key={type} disabled={content.blocks.length >= 300} onClick={() => onChange({ ...content, blocks: [...content.blocks, { block_id: `noteblock_${crypto.randomUUID().replace(/-/g, '')}`, type, data: type === 'heading' ? { text: '新标题', level: 2 } : type === 'equation' ? { latex: 'x', annotation: '' } : type === 'list' ? { ordered: false, items: ['新列表项'] } : { markdown: '新段落', ...(type === 'callout' ? { tone: 'info' } : {}) }, source_ref_ids: [], evidence_ref_ids: [] }] })}>添加{({ paragraph: '段落', heading: '标题', equation: '公式', list: '列表', callout: '提示' })[type]}</button>)}</div></div>;
}
