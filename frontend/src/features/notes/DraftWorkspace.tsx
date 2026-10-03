import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { post } from '../../api/client';
import { NoteApiError, notesApi, noteRequest } from './api';
import { useNoteEditor } from './hooks/useNoteEditor';
import { BlockEditor, NoteBlocks } from './NoteBlocks';
import type { ChapterRef, NoteDraft } from './types';
import './notes.css';
export function DraftEditor({ draft }: {
    draft: NoteDraft;
}) {
    const { editor, change: update } = useNoteEditor(draft);
    const navigate = useNavigate();
    const [editing, setEditing] = useState(draft.kind !== 'generation');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [saveConflict, setSaveConflict] = useState(false);
    const [extraChapters, setExtraChapters] = useState<ChapterRef[]>([]);
    const change = (content: typeof editor.content) => {
        if (!saveConflict) setError('');
        update(content);
    };
    const op = useRef<{
        key: string;
        id: string;
    } | null>(null);
    const local = editor.content;
    const save = async () => {
        setSaving(true);
        setError('');
        setSaveConflict(false);
        try {
            await editor.flush();
            const current = editor.draft;
            const key = `${current.draft_revision}:${current.content!.quality.warning_hash}`;
            if (!op.current || op.current.key !== key)
                op.current = { key, id: crypto.randomUUID() };
            const saved = await notesApi.save(draft.id, { operation_id: op.current.id, expected_draft_revision: current.draft_revision, base_note_revision: current.base_note_revision });
            navigate(`/notes/${saved.note_id}`);
        }
        catch (e) {
            setSaveConflict(e instanceof NoteApiError && e.code === 'revision_conflict');
            setError(e instanceof Error ? e.message : '保存失败');
        }
        finally {
            setSaving(false);
        }
    };
    return <div className="management-workspace notes-workspace"><header className="app-page-header note-page-header window-drag-region"><h1>{draft.base_note_id ? '编辑笔记' : '笔记草稿'}</h1><div className="note-actions"><span role="status" className="note-save-status">{({ saved: '草稿已保存', dirty: '有未保存修改', saving: '正在保存草稿…', error: '草稿保存失败' })[editor.state]}</span><Link className="app-ghost-button" to="/notes?view=drafts">返回笔记</Link><button className="app-secondary-button" onClick={() => setEditing(v => !v)}>{editing ? '阅读预览' : '逐块编辑'}</button><button className="app-primary-button" disabled={saving || editor.closing || editor.state === 'saving'} onClick={() => void save()}>{saving ? '正在保存…' : draft.base_note_id ? '保存修改' : '保存笔记'}</button></div></header>
    <div className="note-scroll"><article className="note-document">
      <h1 className="note-document-title">{local.title}</h1>{!editing && local.abstract && <p className="note-abstract">{local.abstract}</p>}
      {error && !saveConflict && <p role="alert" className="note-warning">{error}</p>}{(editor.error || saveConflict) && <div role="alert" className="note-warning"><p>{editor.error || error}</p><div className="note-actions"><button className="app-secondary-button" onClick={() => void editor.flush().catch(() => { })}>重试保存草稿</button><button className="app-secondary-button" onClick={() => void navigator.clipboard.writeText(JSON.stringify(local, null, 2)).catch(() => setError('复制失败，请选择正文复制'))}>复制当前修改</button><button className="app-secondary-button" onClick={async () => { try {
        await navigator.clipboard.writeText(JSON.stringify(local, null, 2));
        editor.reload(await notesApi.draft(draft.id));
        setError('当前修改已复制，已重新载入服务器草稿。');
    }
    catch (e) {
        setError(e instanceof Error ? e.message : '恢复失败，当前文字仍保留');
    } }}>复制修改并重新载入</button></div><p>当前文字仍保留。可重试保存；如需重新读取草稿，请先复制修改。</p></div>}
      {editing && <fieldset disabled={saving || editor.closing} className="note-fields"><label>标题<input maxLength={200} value={local.title} onChange={e => change({ ...local, title: e.target.value })}/></label><label>摘要<textarea maxLength={500} value={local.abstract} onChange={e => change({ ...local, abstract: e.target.value })}/></label><details><summary>笔记信息</summary><div className="note-fields-row"><label>学科<input value={local.subject} onChange={e => change({ ...local, subject: e.target.value })}/></label><label>标签（逗号分隔）<input value={local.tags.join(',')} onChange={e => change({ ...local, tags: e.target.value.split(/[,，]/).map(t => t.trim()).filter(Boolean) })}/></label></div><button type="button" className="app-ghost-button" onClick={() => void noteRequest<{
        items: ChapterRef[];
    }>("/chapters").then(page => setExtraChapters(page.items)).catch(e => setError(e.message))}>选择其他教材章节</button>{(draft.chapter_options.length > 0 || extraChapters.length > 0 || local.chapter_refs.length > 0) && <details><summary>归入章节</summary>{Array.from(new Map([...draft.chapter_options, ...extraChapters, ...local.chapter_refs].map(c => [c.chapter_ref_id, c])).values()).map(c => <label className="note-checkbox" key={c.chapter_ref_id}><input type="checkbox" checked={local.chapter_refs.some(r => r.chapter_ref_id === c.chapter_ref_id)} onChange={e => change({ ...local, chapter_refs: e.target.checked ? [...local.chapter_refs, c] : local.chapter_refs.filter(r => r.chapter_ref_id !== c.chapter_ref_id) })}/>{c.book_name_snapshot} · {c.title_snapshot}</label>)}</details>}</details></fieldset>}
      {editing ? <fieldset disabled={saving || editor.closing} className="note-fields"><BlockEditor content={local} onChange={change}/></fieldset> : <NoteBlocks blocks={local.blocks}/>}
    </article></div></div>;
}
export function GenerationWorkspace({ draft, reload }: {
    draft: NoteDraft;
    reload: () => Promise<void>;
}) {
    const navigate = useNavigate();
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const retryOp = useRef<string | null>(null);
    const terminal = Boolean(draft.recovery_error) || (draft.job && ['failed', 'cancelled', 'interrupted'].includes(draft.job.status));
    const status = draft.job?.status;
    const heading = status === 'cancelled' ? '生成已取消' : status === 'interrupted' ? '生成已中断' : terminal ? '生成未完成' : status === 'cancelling' ? '正在停止' : status === 'queued' ? '等待开始整理' : '正在整理学习内容';
    const message = draft.recovery_error ? '保存的生成结果未通过发布检查，请重试或手动整理。' : status === 'cancelling' ? '正在取消生成，停止后可从保存的来源重试或手动整理。' : status === 'interrupted' ? '生成已中断，来源已保留；不会自动重跑模型。' : status === 'cancelled' ? '生成已停止，来源已保留；可重试或手动整理。' : status === 'failed' ? '这次整理未能完成，来源已保留；可重试或手动整理。' : status === 'queued' ? '任务正在等待处理，可返回会话继续学习。' : draft.job?.message || '正在准备会话内容…';
    const action = async (kind: 'cancel' | 'retry' | 'manual' | 'discard') => {
        setBusy(true);
        setError('');
        try {
            if (kind === 'cancel') {
                const result = await post(`/jobs/${draft.job_id}/cancel`, {});
                if (!result.success) throw new Error(result.message || '取消未确认，请稍后重试。');
                await reload();
            }
            if (kind === 'retry') {
                retryOp.current ||= crypto.randomUUID();
                const r = await notesApi.generate({ operation_id: retryOp.current, retry_of_draft_id: draft.id });
                navigate(`/notes/drafts/${r.draft_id}`);
            }
            if (kind === 'manual') {
                const r = await notesApi.createDraft({ kind: 'manual', snapshot_id: draft.source_snapshot_ids[0] });
                navigate(`/notes/drafts/${r.id}`);
            }
            if (kind === 'discard') {
                if (!window.confirm('丢弃这份未完成的笔记草稿？来源会话不受影响。')) return;
                await noteRequest(`/drafts/${draft.id}/discard`, 'POST', {});
                navigate('/notes?view=drafts');
            }
        }
        catch (e) {
            setError(e instanceof Error ? e.message : '操作失败');
        }
        finally {
            setBusy(false);
        }
    };
    return <div className="management-workspace notes-workspace"><header className="app-page-header note-page-header window-drag-region"><h1>整理笔记</h1><Link className="app-ghost-button" to="/notes?view=drafts">草稿列表</Link></header><div className="note-scroll"><article className="note-document"><h2>{heading}</h2><p role="status">{message}</p><p>{terminal ? '正式笔记须审阅后保存。你也可以返回会话继续学习。' : '可返回会话继续学习。生成在本地后台运行，正式笔记须审阅后保存。'}</p>{error && <p className="note-warning" role="alert">{error}</p>}<div className="note-actions">{terminal ? <><button disabled={busy} className="app-primary-button" onClick={() => void action('retry')}>从同一来源重试</button><button disabled={busy} className="app-secondary-button" onClick={() => void action('manual')}>手动整理</button><button disabled={busy} className="app-ghost-button" onClick={() => void action('discard')}>丢弃草稿</button></> : <button disabled={busy || draft.job?.status === 'cancelling'} className="app-secondary-button" onClick={() => void action('cancel')}>取消生成</button>}<Link className="app-ghost-button" to={`/?conversation_id=${encodeURIComponent(draft.conversation_id)}`}>返回会话</Link></div></article></div></div>;
}
