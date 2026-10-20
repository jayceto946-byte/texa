import { ChevronRight } from 'lucide-react';
import WorkspaceSkeleton from '../components/ui/WorkspaceSkeleton';
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
        return <div className="management-workspace notes-workspace"><header className="app-page-header note-page-header window-drag-region"><h1>笔记</h1><Link className="app-ghost-button" to="/notes">笔记列表</Link></header><div className="management-page-content"><>{error ? <p role="alert">{error}</p> : <WorkspaceSkeleton label="正在读取笔记" header={false} reading />}</></div></div>;
    const headings = note.blocks.filter(block => block.type === 'heading');
    const hasContents = headings.length > 2;
    return <div className="management-workspace notes-workspace">
      <header className="app-page-header note-page-header window-drag-region">
        <div className="note-header-identity">
          <h1>笔记</h1>
          <span className="note-header-state" role="status">{revision ? `历史版本 ${revision} · 只读` : `已保存 · 版本 ${note.revision}`}{note.status === 'archived' ? ' · 已归档' : ''}</span>
        </div>
        <div className="note-actions">
          <Link className="app-ghost-button" to="/notes">返回笔记</Link>
          {!revision && <>
            <button className="app-primary-button" disabled={busy || note.status !== 'active'} onClick={() => void edit()}>编辑</button>
            <button className="app-secondary-button" disabled={busy} onClick={() => void status()}>{note.status === 'active' ? '归档' : '恢复'}</button>
          </>}
          {revision && <Link className="app-secondary-button" to={`/notes/${note.id}`}>当前版本</Link>}
        </div>
      </header>
      <div className="note-scroll" ref={scrollRef} onScroll={rememberScroll}><article className="note-document">
        <h1 className="note-document-title">{note.title}</h1>
        {error && <p role="alert" className="note-warning">{error}</p>}
        {note.abstract && <p className="note-abstract">{note.abstract}</p>}
        <details className="note-meta-details">
          <summary><ChevronRight size={14} aria-hidden="true"/>{hasContents ? '目录与笔记信息' : '笔记信息'}</summary>
          <div className="note-meta-content">
            {hasContents && <nav aria-label="笔记目录"><h2>目录</h2>{headings.map(block => <a className="note-toc-link" key={block.block_id} href={`#${block.block_id}`}>{block.data.text}</a>)}</nav>}
            <div>
              {hasContents && <h2>笔记信息</h2>}
              <dl className="note-meta-facts">
                <dt>整理至</dt><dd><time dateTime={note.origins[0].captured_at}>{new Date(note.origins[0].captured_at).toLocaleString()}</time></dd>
                <dt>保存于</dt><dd><time dateTime={note.updated_at}>{new Date(note.updated_at).toLocaleString()}</time></dd>
                <dt>版本</dt><dd>{note.revision}</dd>
                {note.subject && <><dt>学科</dt><dd>{note.subject}</dd></>}
                {note.tags.length > 0 && <><dt>标签</dt><dd>{note.tags.join('、')}</dd></>}
              </dl>
              {note.chapter_refs.map(c => <p key={c.chapter_ref_id} className="note-caption">{c.book_name_snapshot} · {c.title_snapshot}</p>)}
            </div>
          </div>
        </details>
    <NoteBlocks blocks={note.blocks}/>
    <details onToggle={e => { if (e.currentTarget.open && !history.length)
        void revisions(); }}><summary>保存的历史版本</summary><div className="note-actions">{history.map(r => <Link className="app-ghost-button" key={r.revision} to={`/notes/${noteId}?revision=${r.revision}`}>版本 {r.revision} · {new Date(r.saved_at).toLocaleString()}</Link>)}</div>{historyCursor && <button className="app-ghost-button" onClick={() => void revisions(historyCursor)}>更早版本</button>}</details>
  </article></div></div>;
}
