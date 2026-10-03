import { Link, useParams } from 'react-router-dom';
import { useDraftWorkspace } from '../features/notes/hooks/useDraftWorkspace';
import { DraftEditor, GenerationWorkspace } from '../features/notes/DraftWorkspace';
import { unsavedNotePath } from '../features/notes/autosave';
import type { ReactNode } from 'react';
function DraftState({ children }: { children: ReactNode }) {
    return <div className="management-workspace notes-workspace"><header className="app-page-header note-page-header window-drag-region"><h1>笔记草稿</h1><Link className="app-ghost-button" to="/notes?view=drafts">草稿列表</Link></header><div className="management-page-content">{children}</div></div>;
}
export default function NoteDraftPage() {
    const { draftId = '' } = useParams();
    const { draft, error, reload } = useDraftWorkspace(draftId);
    const retainedPath = unsavedNotePath();
    if (retainedPath && retainedPath !== `/notes/drafts/${draftId}`)
        return <DraftState><p role="alert">另一份草稿有尚未保存的修改，请先处理，避免丢失内容。</p><Link className="app-primary-button" to={retainedPath}>回到未保存草稿</Link></DraftState>;
    if (error)
        return <DraftState><p role="alert">{error}</p><button className="app-secondary-button" onClick={() => void reload()}>重新读取</button></DraftState>;
    if (!draft)
        return <DraftState><p role="status">正在读取草稿…</p></DraftState>;
    if (draft.status === 'published')
        return <DraftState><p>草稿已保存成笔记。</p><Link className="app-primary-button" to={`/notes/${draft.published_note_id}`}>打开笔记</Link></DraftState>;
    if (draft.status === 'discarded')
        return <DraftState><p>草稿已丢弃。</p><Link to="/notes">返回笔记</Link></DraftState>;
    if (draft.status === 'editable')
        return <DraftEditor key={draft.id} draft={draft}/>;
    return <GenerationWorkspace draft={draft} reload={reload}/>;
}
