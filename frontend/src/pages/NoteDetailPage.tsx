import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useNoteScroll } from '../features/notes/hooks/useNoteScroll';
import { useNoteDetail } from '../features/notes/hooks/useNoteDetail';
import { NoteBlocks } from '../features/notes/NoteBlocks';
import '../features/notes/notes.css';
export default function NoteDetailPage() {
    const { noteId = '' } = useParams();
    const [params] = useSearchParams();
    const revision = params.get('revision') || undefined;
    const { note, error, busy, history, historyCursor, edit, status, revisions } = useNoteDetail(noteId, revision);
    const { ref: scrollRef, onScroll: rememberScroll } = useNoteScroll(`${noteId}:${revision || 'current'}`, Boolean(note));
    if (!note)
        return <div className="management-workspace notes-workspace"><header className="app-page-header note-page-header window-drag-region"><h1>笔记</h1><Link className="app-ghost-button" to="/notes">笔记列表</Link></header><div className="management-page-content"><p role={error ? 'alert' : 'status'}>{error || '正在读取笔记…'}</p></div></div>;
    return <div className="management-workspace notes-workspace"><header className="app-page-header note-page-header window-drag-region"><h1>笔记</h1><span className="note-header-state">{revision ? `历史版本 ${revision} · 只读` : `已保存 · 版本 ${note.revision}`} {note.status === 'archived' ? '· 已归档' : ''}</span><div className="note-actions"><Link className="app-ghost-button" to="/notes">笔记列表</Link>{!revision && <><button className="app-primary-button" disabled={busy || note.status !== 'active'} onClick={() => void edit()}>编辑</button><button className="app-secondary-button" disabled={busy} onClick={() => void status()}>{note.status === 'active' ? '归档' : '恢复'}</button></>}{revision && <Link className="app-secondary-button" to={`/notes/${note.id}`}>当前版本</Link>}</div></header><div className="note-scroll" ref={scrollRef} onScroll={rememberScroll}><article className="note-document">
    <h1 className="note-document-title">{note.title}</h1>{error && <p role="alert" className="note-warning">{error}</p>}
    {note.abstract && <p className="note-abstract">{note.abstract}</p>}
    <details><summary>笔记信息</summary><p className="note-caption">整理至 {new Date(note.origins[0].captured_at).toLocaleString()} · 保存于 {new Date(note.updated_at).toLocaleString()} · 版本 {note.revision}</p><p className="note-caption">{note.subject} · {note.tags.join('、')}</p>{note.chapter_refs.map(c => <p key={c.chapter_ref_id} className="note-caption">{c.book_name_snapshot} · {c.title_snapshot}</p>)}</details>
    {note.blocks.filter(b => b.type === 'heading').length > 2 && <details><summary>目录</summary>{note.blocks.filter(b => b.type === 'heading').map(b => <a className="note-toc-link" key={b.block_id} href={`#${b.block_id}`}>{b.data.text}</a>)}</details>}
    <NoteBlocks blocks={note.blocks}/>
    <details onToggle={e => { if (e.currentTarget.open && !history.length)
        void revisions(); }}><summary>保存的历史版本</summary><div className="note-actions">{history.map(r => <Link className="app-ghost-button" key={r.revision} to={`/notes/${noteId}?revision=${r.revision}`}>版本 {r.revision} · {new Date(r.saved_at).toLocaleString()}</Link>)}</div>{historyCursor && <button className="app-ghost-button" onClick={() => void revisions(historyCursor)}>更早版本</button>}</details>
  </article></div></div>;
}
