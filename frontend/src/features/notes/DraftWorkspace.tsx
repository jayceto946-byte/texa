import { useLayoutEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { post } from '../../api/client';
import { NoteApiError, notesApi, noteRequest } from './api';
import { useNoteEditor } from './hooks/useNoteEditor';
import { useDraftPosition } from './hooks/useDraftPosition';
import { NoteTextarea } from './NoteTextarea';
import { BlockEditor, NoteBlocks } from './NoteBlocks';
import type { ChapterRef, NoteDraft } from './types';
import './notes.css';
export function DraftEditor({ draft }: {
    draft: NoteDraft;
}) {
    const { editor, change: update } = useNoteEditor(draft);
    const navigate = useNavigate();
    const location = useLocation();
    const [editing, setEditing] = useState(draft.kind !== 'generation');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [saveConflict, setSaveConflict] = useState(false);
    const [formalConflict, setFormalConflict] = useState(false);
    const [recovering, setRecovering] = useState(false);
    const [recoveryError, setRecoveryError] = useState('');
    const [latestArchived, setLatestArchived] = useState(false);
    const draftConflict = editor.errorCode === 'revision_conflict';
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
    const { scrollRef, capture: capturePosition, rememberFocus } = useDraftPosition(editing);
    const undoRef = useRef<HTMLButtonElement>(null);
    const recoveryFocus = useRef<string | null>(null);
    useLayoutEffect(() => {
        const target = recoveryFocus.current;
        recoveryFocus.current = null;
        if (target === 'undo') undoRef.current?.focus();
        else if (target) document.getElementById(target)?.focus();
    });
    const removeBlock = (index: number) => {
        recoveryFocus.current = 'undo';
        if (!editor.deleteBlock(index)) recoveryFocus.current = null;
    };
    const undoDelete = () => {
        const id = editor.undoDelete();
        if (id) {
            recoveryFocus.current = id;
            setEditing(true);
        }
    };
    const save = async () => {
        setSaving(true);
        setError('');
        setSaveConflict(false);
        setFormalConflict(false);
        let publishing = false;
        try {
            await editor.flush();
            const current = editor.draft;
            const key = `${current.draft_revision}:${current.content!.quality.warning_hash}`;
            if (!op.current || op.current.key !== key)
                op.current = { key, id: crypto.randomUUID() };
            publishing = true;
            const saved = await notesApi.save(draft.id, { operation_id: op.current.id, expected_draft_revision: current.draft_revision, base_note_revision: current.base_note_revision });
            navigate(`/notes/${saved.note_id}`);
        }
        catch (e) {
            setSaveConflict(e instanceof NoteApiError && e.code === 'revision_conflict');
            setFormalConflict(publishing && Boolean(editor.draft.base_note_id) && e instanceof NoteApiError && e.code === 'revision_conflict');
            setError(e instanceof Error ? e.message : '保存失败');
            if (publishing && editor.draft.base_note_id && e instanceof NoteApiError && e.code === 'revision_conflict') {
                try { setLatestArchived((await notesApi.note(editor.draft.base_note_id)).status !== 'active'); } catch { /* Recovery retries the read without losing content. */ }
            }
        }
        finally {
            setSaving(false);
        }
    };
    const recover = async () => {
        if (recovering || saving || editor.state === 'saving') return;
        setRecovering(true);
        setRecoveryError('');
        try {
            // Copy succeeds before changing the visible authority; never overwrite it.
            await navigator.clipboard.writeText(JSON.stringify(local, null, 2));
            if (formalConflict && editor.draft.base_note_id) {
                const latest = await notesApi.note(editor.draft.base_note_id);
                if (latest.status !== 'active') {
                    navigate(`/notes/${latest.id}`);
                } else {
                    const next = await notesApi.createDraft({ kind: 'edit', note_id: latest.id, base_revision: latest.revision });
                    navigate(`/notes/drafts/${next.id}`, { state: { noteRecovery: '修改已复制，正在编辑最新版本。请人工整理后保存。' } });
                }
            } else {
                editor.reload(await notesApi.draft(draft.id));
                setSaveConflict(false);
                setFormalConflict(false);
                setError('当前修改已复制，已重新载入服务器草稿。');
            }
        } catch (e) {
            setRecoveryError(`恢复未完成，当前文字仍保留。${e instanceof Error ? e.message : ''}`);
        } finally { setRecovering(false); }
    };
    return <div className="management-workspace notes-workspace"><header className="app-page-header note-page-header window-drag-region"><div className="note-header-identity"><h1>{draft.base_note_id ? '编辑笔记' : draft.kind === 'generation' ? '对话整理笔记' : '自主整理笔记'}</h1><span role="status" className="note-save-status">{formalConflict ? '正式笔记尚未更新 · ' : ''}{({ saved: '草稿已保存', dirty: '有未保存修改', saving: '正在保存草稿…', error: '草稿保存失败' })[editor.state]}</span></div><div className="note-actions"><Link className="app-ghost-button" to="/notes?view=drafts">返回笔记</Link><button className="app-secondary-button" aria-controls="note-draft-body" onClick={() => { capturePosition(); setEditing(v => !v); }}>{editing ? '阅读预览' : '编辑笔记'}</button><button className="app-primary-button" disabled={saving || recovering || formalConflict || editor.closing || editor.state === 'saving'} onClick={() => void save()}>{saving ? '正在保存…' : draft.base_note_id ? '保存修改' : '保存笔记'}</button></div></header>
    <div className="note-scroll" ref={scrollRef} onFocusCapture={e => rememberFocus(e.target)}>
      {editor.deletedCount > 0 && <div className="note-delete-recovery"><span role="status">已删除 {editor.deletedCount} 块 · 本次编辑可撤销</span><button ref={undoRef} className="app-secondary-button" disabled={saving || recovering || editor.closing || local.blocks.length >= 300} onClick={undoDelete}>撤销删除</button>{local.blocks.length >= 300 && <span>块数已达上限，请先腾出位置。</span>}</div>}
      <article className="note-document" id="note-draft-body">
      {!editing && <h1 className="note-document-title">{local.title}</h1>}{!editing && local.abstract && <p className="note-abstract">{local.abstract}</p>}
      {location.state?.noteRecovery && <p role="status" className="note-save-status">{location.state.noteRecovery}</p>}
      {error && !saveConflict && !editor.error && <p role="status" className="note-warning">{error}</p>}
      {(editor.error || saveConflict) && <div role="alert" className="note-warning">
        <h2 className="type-section-title">{formalConflict ? '正式笔记版本已变化' : draftConflict ? '草稿已在其他位置更新' : '草稿尚未保存'}</h2>
        <p>{formalConflict ? latestArchived ? '最新笔记已归档。当前修改保留在这份草稿，可复制后查看最新笔记。' : '当前修改已保存在这份草稿，正式笔记没有被覆盖。复制后编辑最新版本，再人工整理这些修改。' : draftConflict ? '当前文字仍保留。先复制修改，再重新载入服务器草稿。' : '当前文字仍保留，离开前请重试保存草稿。'}</p>
        {recoveryError && <p>{recoveryError}</p>}
        <div className="note-actions">
          {formalConflict || draftConflict ? <button disabled={recovering || editor.state === 'saving'} className="app-primary-button" onClick={() => void recover()}>{recovering ? '正在保留修改…' : formalConflict ? latestArchived ? '复制修改并查看最新笔记' : '复制修改并编辑最新版本' : '复制修改并重新载入草稿'}</button> : <button disabled={recovering} className="app-primary-button" onClick={() => void editor.flush().catch(() => { })}>重试保存草稿</button>}
          <button disabled={recovering} className="app-secondary-button" onClick={() => void navigator.clipboard.writeText(JSON.stringify(local, null, 2)).catch(() => setRecoveryError('复制失败，请选择正文复制'))}>复制当前修改</button>
        </div>
        <details><summary>错误详情</summary><p>{editor.error || error}</p></details>
      </div>}
      {editing && <fieldset disabled={saving || recovering || editor.closing} className="note-fields"><label className="note-title-field"><span className="note-visually-hidden">标题</span><NoteTextarea className="note-title-input" maxLength={200} value={local.title} onChange={e => change({ ...local, title: e.target.value })}/></label><label>摘要<NoteTextarea maxLength={500} value={local.abstract} onChange={e => change({ ...local, abstract: e.target.value })}/></label><details><summary>笔记信息</summary><div className="note-fields-row"><label>学科<input value={local.subject} onChange={e => change({ ...local, subject: e.target.value })}/></label><label>标签（逗号分隔）<input value={local.tags.join(',')} onChange={e => change({ ...local, tags: e.target.value.split(/[,，]/).map(t => t.trim()).filter(Boolean) })}/></label></div><button type="button" className="app-ghost-button" onClick={() => void noteRequest<{
        items: ChapterRef[];
    }>("/chapters").then(page => setExtraChapters(page.items)).catch(e => setError(e.message))}>选择其他教材章节</button>{(draft.chapter_options.length > 0 || extraChapters.length > 0 || local.chapter_refs.length > 0) && <details><summary>归入章节</summary>{Array.from(new Map([...draft.chapter_options, ...extraChapters, ...local.chapter_refs].map(c => [c.chapter_ref_id, c])).values()).map(c => <label className="note-checkbox" key={c.chapter_ref_id}><input type="checkbox" checked={local.chapter_refs.some(r => r.chapter_ref_id === c.chapter_ref_id)} onChange={e => change({ ...local, chapter_refs: e.target.checked ? [...local.chapter_refs, c] : local.chapter_refs.filter(r => r.chapter_ref_id !== c.chapter_ref_id) })}/>{c.book_name_snapshot} · {c.title_snapshot}</label>)}</details>}</details></fieldset>}
      {editing ? <fieldset disabled={saving || recovering || editor.closing} className="note-fields"><BlockEditor content={local} onChange={change} onDelete={removeBlock}/></fieldset> : <NoteBlocks blocks={local.blocks}/>}
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
    const message = draft.recovery_error ? '保存的生成结果未通过发布检查，请重试或手动整理。' : status === 'cancelling' ? '正在取消生成，停止后可从保存的来源重试或手动整理。' : status === 'interrupted' ? '生成已中断，来源已保留；不会自动重跑模型。' : status === 'cancelled' ? '生成已停止，来源已保留；可重试或手动整理。' : status === 'failed' ? draft.job?.message || '这次整理未能完成，来源已保留；可重试或手动整理。' : status === 'queued' ? '任务正在等待处理，可返回会话继续学习。' : draft.job?.message || '正在准备会话内容…';
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
    return <div className="management-workspace notes-workspace"><header className="app-page-header note-page-header window-drag-region"><h1>整理笔记</h1><Link className="app-ghost-button" to="/notes?view=drafts">草稿列表</Link></header><div className="note-scroll"><article className="note-document"><h2>{heading}</h2><p role="status">{message}</p><p>{terminal ? '可重试生成，或手动整理后保存。' : '可返回会话继续学习。生成完成后可直接阅读，选择保存后进入笔记库。'}</p>{error && <p className="note-warning" role="alert">{error}</p>}<div className="note-actions">{terminal ? <><button disabled={busy} className="app-primary-button" onClick={() => void action('retry')}>从同一来源重试</button><button disabled={busy} className="app-secondary-button" onClick={() => void action('manual')}>手动整理</button><button disabled={busy} className="app-ghost-button" onClick={() => void action('discard')}>丢弃草稿</button></> : <button disabled={busy || draft.job?.status === 'cancelling'} className="app-secondary-button" onClick={() => void action('cancel')}>取消生成</button>}<Link className="app-ghost-button" to={`/?conversation_id=${encodeURIComponent(draft.conversation_id)}`}>返回会话</Link></div></article></div></div>;
}
