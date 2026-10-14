import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { notesApi } from '../api';
import type { NoteDraft } from '../types';
export function useDraftWorkspace(id: string) {
    const location = useLocation();
    const active = location.pathname === `/notes/drafts/${id}`;
    const [draft, setDraft] = useState<NoteDraft | null>(null);
    const [error, setError] = useState('');
    const reload = useCallback(async () => {
        try {
            setDraft(await notesApi.draft(id));
            setError('');
        }
        catch (e) {
            setError(e instanceof Error ? e.message : '草稿读取失败');
        }
    }, [id]);
    useEffect(() => {
        if (!active)
            return;
        setDraft(null);
        setError('');
        const controller = new AbortController();
        let timer: ReturnType<typeof setTimeout>;
        const load = async () => {
            try {
                const value = await notesApi.draft(id, controller.signal);
                if (controller.signal.aborted)
                    return;
                setDraft(value);
                setError('');
                if (value.status === 'preparing' && !value.recovery_error && (!value.job || ['queued', 'running', 'cancelling'].includes(value.job.status)))
                    timer = setTimeout(() => void load(), 2000);
            }
            catch (e) {
                if (!controller.signal.aborted)
                    setError(e instanceof Error ? e.message : '草稿读取失败');
            }
        };
        void load();
        return () => { controller.abort(); clearTimeout(timer); };
    }, [id, active]);
    return { draft, error, reload };
}
