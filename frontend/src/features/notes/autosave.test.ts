import { describe, expect, it } from 'vitest';
import { DraftAutosaver, editableContent, retainEditor, unsavedNotePath, flushRetainedEditor } from './autosave';
import type { NoteDraft } from './types';
function draft(revision = 1, title = 'original'): NoteDraft {
    return { id: 'draft', kind: 'manual', status: 'editable', draft_revision: revision, conversation_id: 'session', base_note_id: null, base_note_revision: null, job_id: null, source_snapshot_ids: ['snap'], sources: [], chapter_options: [], content: { title, abstract: '', subject: '', tags: [], chapter_refs: [], blocks: [], quality: { warnings: [], warning_hash: 'hash', semantic_review: 'not_checked' } } };
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
describe('serial note autosave', () => {
    it('does not overwrite newer local text with a stale response', async () => {
        const pending = deferred<NoteDraft>();
        const writes: {
            revision: number;
            title: string;
        }[] = [];
        const saver = new DraftAutosaver(draft(), async (revision, content) => { writes.push({ revision, title: content.title }); if (writes.length === 1)
            return pending.promise; return draft(revision + 1, content.title); });
        saver.change({ ...saver.content, title: 'first' });
        const flush = saver.flush();
        saver.change({ ...saver.content, title: 'second' });
        expect(saver.content.title).toBe('second');
        pending.resolve(draft(2, 'first'));
        await flush;
        expect(saver.content.title).toBe('second');
        expect(saver.draft.draft_revision).toBe(3);
        expect(writes).toEqual([{ revision: 1, title: 'first' }, { revision: 2, title: 'second' }]);
        expect(saver.dirty).toBe(false);
        saver.stopTimer();
    });
    it('retains text on CAS failures and retries with the same revision', async () => {
        let fail = true;
        const versions: number[] = [];
        const saver = new DraftAutosaver(draft(), async (revision, content) => { versions.push(revision); if (fail)
            throw new Error('revision conflict'); return draft(2, content.title); });
        saver.change({ ...saver.content, title: 'unsaved' });
        await expect(saver.flush()).rejects.toThrow('revision conflict');
        expect(saver.dirty).toBe(true);
        expect(saver.content.title).toBe('unsaved');
        retainEditor('draft', saver);
        expect(unsavedNotePath()).toBe('/notes/drafts/draft');
        fail = false;
        await saver.flush();
        retainEditor('draft', saver);
        expect(versions).toEqual([1, 1]);
        expect(unsavedNotePath()).toBe(null);
        saver.stopTimer();
    });
    it('keeps a vetoed browser refresh editable and freezes a native close until aborted', async () => {
        const saver = new DraftAutosaver(draft(), async (revision, content) => draft(revision + 1, content.title));
        saver.change({ ...saver.content, title: 'refresh' });
        retainEditor('draft', saver);
        await expect(flushRetainedEditor(false, false)).resolves.toBe(true);
        expect(saver.closing).toBe(false);
        saver.change({ ...saver.content, title: 'close' });
        retainEditor('draft', saver);
        await expect(flushRetainedEditor()).resolves.toBe(true);
        expect(saver.closing).toBe(true);
        await flushRetainedEditor(true);
        expect(saver.closing).toBe(false);
        retainEditor('draft', saver);
        saver.stopTimer();
    });
    it('coalesces concurrent flushes and excludes server quality from editable requests', async () => {
        const pending = deferred<NoteDraft>();
        let writes = 0;
        const saver = new DraftAutosaver(draft(), async () => { writes++; return pending.promise; });
        saver.change({ ...saver.content, title: 'changed' });
        const a = saver.flush();
        const b = saver.flush();
        expect(a).toBe(b);
        pending.resolve(draft(2, 'changed'));
        await a;
        expect(writes).toBe(1);
        expect(editableContent(saver.draft)).not.toHaveProperty('quality');
        saver.stopTimer();
    });
});
