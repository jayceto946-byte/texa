import { useEffect, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { noteRequest } from '../api';
import type { ChapterRef, Note, NoteDraft } from '../types';
export function useNotesList() {
    const [params, setParams] = useSearchParams();
    const location = useLocation();
    const view = params.get('view') || 'saved';
    const signature = params.toString();
    const [page, setPage] = useState<{
        items: (Note | NoteDraft & {
            title: string;
            updated_at: string;
        })[];
        next_cursor: string | null;
    }>({ items: [], next_cursor: null });
    const [refresh, setRefresh] = useState(0);
    const [error, setError] = useState('');
    const [filterOptions, setFilterOptions] = useState<{chapter_refs: ChapterRef[]; books: {book_id: string; name: string}[]}>({ chapter_refs: [], books: [] });
    const [filterError, setFilterError] = useState('');
    useEffect(() => {
        if (location.pathname !== '/notes' || view === 'drafts') return;
        let active = true;
        void noteRequest<typeof filterOptions>(`/filters?status=${view === 'archived' ? 'archived' : 'active'}`).then(value => { if (active) { setFilterOptions(value); setFilterError(''); } }).catch(() => { if (active) setFilterError('教材与章节选项暂不可用，仍可读取笔记。'); });
        return () => { active = false; };
    }, [view, location.pathname, refresh]);
    const [loading, setLoading] = useState(false);
    const [undo, setUndo] = useState<{
        id: string;
        revision: number;
        status: string;
    } | null>(null);
    const [busy, setBusy] = useState(false);
    useEffect(() => {
        if (location.pathname !== '/notes')
            return;
        let active = true;
        const query = new URLSearchParams(signature);
        query.delete('view');
        if (view !== 'drafts')
            query.set('status', view === 'archived' ? 'archived' : 'active');
        setLoading(true);
        setError('');
        void noteRequest<typeof page>(`${view === 'drafts' ? '/drafts' : ''}?${query}`).then(value => { if (active)
            setPage(value); }).catch(e => { if (active)
            setError(e.message); }).finally(() => { if (active)
            setLoading(false); });
        return () => { active = false; };
    }, [signature, view, refresh, location.pathname]);
    const filter = (key: string, value: string) => { const next = new URLSearchParams(params); next.delete('cursor'); if (value)
        next.set(key, value);
    else
        next.delete(key); setParams(next); };
    const changeStatus = async (id: string, revision: number, status: string) => { setBusy(true); try {
        const r = await noteRequest<{
            revision: number;
        }>(`/${id}/status`, 'PATCH', { operation_id: crypto.randomUUID(), expected_revision: revision, status });
        setUndo({ id, revision: r.revision, status: status === 'archived' ? 'active' : 'archived' });
        setRefresh(v => v + 1);
    }
    catch (e) {
        setError(e instanceof Error ? e.message : '操作失败');
    }
    finally {
        setBusy(false);
    } };
    const notes = page.items.filter((item): item is Note => 'revision' in item);
    return { params, setParams, view, page, error, loading, busy, undo, setUndo, setRefresh, filter, changeStatus, notes, filterOptions, filterError };
}
