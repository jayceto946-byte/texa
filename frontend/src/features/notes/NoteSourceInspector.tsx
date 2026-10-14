import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { MarkdownMessage } from '../../components/chat/MarkdownMessage';
import { notesApi } from './api';
import type { SourceDetail, NoteBlock } from './types';
import { SourceGroupList } from '../../components/chat/SourceGroupList';
import { reviewReason } from './labels';
import { groupSourcesByLocation } from '../../utils/citations';
export default function NoteSourceInspector({ id, ids, draft = false, revision, block }: {
    id: string;
    ids: string[];
    draft?: boolean;
    revision?: string;
    block?: NoteBlock;
}) {
    const returnPath = `/notes/${draft ? 'drafts/' : ''}${id}${!draft && revision ? `?revision=${revision}` : ''}`;
    const statusLabel: Record<string, string> = { complete: '已完成', partial: '未完成', interrupted: '已中断', error: '失败', waiting: '等待输入', unknown: '未知', degraded: '降级', unverified: '未核实', verified: '通过发布检查', supported: '有支持', unsupported: '缺少支持', not_checked: '未检查' };
    const label = (value?: string) => value ? statusLabel[value] || '待检查' : '未检查';
    const [sources, setSources] = useState<SourceDetail[]>([]);
    const [error, setError] = useState('');
    useEffect(() => {
        let active = true;
        setSources([]);
        setError('');
        void Promise.all(ids.map(source => notesApi.source(id, source, draft, revision))).then(values => { if (active)
            setSources(values); }).catch(e => { if (active)
            setError(e.message); });
        return () => { active = false; };
    }, [id, ids, draft, revision]);
    return <div className="note-source-inspector">{block && <section><h3>本段来源与核实状态</h3><p>{block.source_alignment === 'user_added' ? '用户补充，未引用会话来源。' : block.source_alignment === 'needs_review' ? '正文经过编辑，来源对应关系需要重新检查。' : '保留整理时的来源对应关系。'}</p>{block.verification?.reasons.map(reason => <p className="note-warning" key={reason}>{reviewReason[reason] || reason}</p>)}</section>}{error && <p role="alert">{error}</p>}{ids.length > 0 && !sources.length && !error && <p role="status">正在读取保存的来源…</p>}{sources.map(detail => <section key={detail.source.source_ref_id}>
    <p className="note-caption">生成时原文 · {detail.source.role === 'user' ? '用户问题' : '助手回答'} · {detail.source.created_at}</p>
    <p className="note-warning">{({ current: '原消息仍可用', changed: '原消息已有变化；下方保留生成时内容', moved: '原消息已移到另一会话', unavailable: '原消息不可用；保存的片段仍可读' })[detail.status] || detail.status}</p>
    <p className="note-caption">回答状态：{label(detail.source.delivery_status)} · 验证：{label(detail.source.learning_task?.verification?.status || detail.source.evidence_support_status)}</p>
    <MarkdownMessage disableRemoteMedia content={detail.source.content}/>
    <SourceGroupList groups={groupSourcesByLocation(detail.evidence.map(e => ({ ...e, id: e.evidence_ref_id })))} cited={false}/>
    {detail.evidence.map(e => <details key={e.evidence_ref_id}><summary>教材 · {e.book_name || '未知教材'} · 来源片段{e.snippet_status === 'unknown' ? '缺失' : '已保存'}</summary><p className="note-caption">索引 {e.index_version || '未知'} · 版本 {e.canonical_hash || '未知'}</p><MarkdownMessage disableRemoteMedia content={e.text || e.snippet || e.excerpt || e.support_text || '历史回答未保存支持片段；不会从当前索引补造。'}/></details>)}
    {detail.live_locator && <Link className="app-secondary-button" to={`/?conversation_id=${encodeURIComponent(detail.live_locator.conversation_id)}&message_id=${encodeURIComponent(detail.live_locator.message_id)}&note_path=${encodeURIComponent(returnPath)}`}>查看当前原会话</Link>}
  </section>)}</div>;
}
