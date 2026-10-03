import { useCallback, useEffect, useReducer, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DraftAutosaver, retainedEditor, retainEditor } from '../autosave';
import { notesApi } from '../api';
import type { NoteContent, NoteDraft } from '../types';
export function useNoteEditor(draft: NoteDraft) {
    const navigate = useNavigate();
    const [, redraw] = useReducer((value: number) => value + 1, 0);
    const [editor] = useState(() => retainedEditor(draft.id) || new DraftAutosaver(draft, (revision, content) => notesApi.patchDraft(draft.id, revision, content)));
    useEffect(() => {
        editor.listen(() => { retainEditor(draft.id, editor); redraw(); });
        const close = (event: BeforeUnloadEvent) => {
            if (!editor.dirty)
                return;
            event.preventDefault();
            event.returnValue = '';
            void editor.flush().catch(() => { });
            navigate(`/notes/drafts/${draft.id}`);
        };
        // Flush before route links so autosave errors leave the editor and text visible.
        const click = (event: MouseEvent) => {
            const anchor = (event.target as Element)?.closest('a[href]') as HTMLAnchorElement | null;
            if (!editor.dirty || !anchor || anchor.origin !== window.location.origin || anchor.target || event.metaKey || event.ctrlKey || anchor.hash)
                return;
            event.preventDefault();
            event.stopPropagation();
            void editor.flush().then(() => navigate(`${anchor.pathname}${anchor.search}`)).catch(() => { });
        };
        window.addEventListener('beforeunload', close);
        document.addEventListener('click', click, true);
        const unsubscribeClose = window.kaoyanDesktop?.onPrepareClose?.(async (aborted) => {
            if (aborted) {
                editor.setClosing(false);
                return false;
            }
            editor.setClosing(true);
            try {
                await editor.flush();
                return true;
            }
            catch {
                editor.setClosing(false);
                navigate(`/notes/drafts/${draft.id}`);
                return false;
            }
        });
        return () => {
            editor.stopTimer();
            retainEditor(draft.id, editor);
            editor.listen(() => retainEditor(draft.id, editor));
            void editor.flush().catch(() => { });
            window.removeEventListener('beforeunload', close);
            document.removeEventListener('click', click, true);
            unsubscribeClose?.();
        };
    }, [draft.id, editor, navigate]);
    const change = useCallback((content: NoteContent) => editor.change(content), [editor]);
    return { editor, change };
}
