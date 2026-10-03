import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { notesApi, noteRequest } from '../api';
import type { Note } from '../types';
export function useNoteDetail(noteId: string, revision?: string) {
    const [note, setNote] = useState<Note | null>(null);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const [history, setHistory] = useState<{
        revision: number;
        saved_at: string;
    }[]>([]);
    const [historyCursor, setHistoryCursor] = useState<number | null>(null);
    const navigate = useNavigate();
    useEffect(() => { let active = true; setNote(null); setHistory([]); setHistoryCursor(null); setError(''); void notesApi.note(noteId, revision).then(n => { if (active) {
        setNote(n);
        setError('');
    } }).catch(e => { if (active)
        setError(e.message); }); return () => { active = false; }; }, [noteId, revision]);
    const edit = async () => { if (!note)
        return; setBusy(true); try {
        const d = await notesApi.createDraft({ kind: 'edit', note_id: note.id, base_revision: note.revision });
        navigate(`/notes/drafts/${d.id}`);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : '编辑失败');
    }
    finally {
        setBusy(false);
    } };
    const status = async () => { if (!note)
        return; setBusy(true); try {
        await noteRequest(`/${note.id}/status`, 'PATCH', { operation_id: crypto.randomUUID(), expected_revision: note.revision, status: note.status === 'active' ? 'archived' : 'active' });
        setNote(await notesApi.note(noteId));
    }
    catch (e) {
        setError(e instanceof Error ? e.message : '操作失败');
    }
    finally {
        setBusy(false);
    } };
    const revisions = async (cursor?: number) => { try {
        const p = await noteRequest<{
            items: typeof history;
            next_cursor: number | null;
        }>(`/${noteId}/revisions${cursor ? `?cursor=${cursor}` : ''}`);
        setHistory(cursor ? [...history, ...p.items] : p.items);
        setHistoryCursor(p.next_cursor);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : '版本读取失败');
    } };
    return { note, error, busy, history, historyCursor, edit, status, revisions };
}
