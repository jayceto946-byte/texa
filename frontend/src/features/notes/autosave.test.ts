import { describe, expect, it } from 'vitest';
import { DraftAutosaver, editableContent, retainEditor, unsavedNotePath, flushRetainedEditor } from './autosave';
import type { NoteBlock, NoteDraft } from './types';
function draft(revision = 1, title = 'original'): NoteDraft {
    return { id: 'draft', kind: 'manual', status: 'editable', draft_revision: revision, conversation_id: 'session', base_note_id: null, base_note_revision: null, job_id: null, source_snapshot_ids: ['snap'], sources: [], chapter_options: [], content: { title, abstract: '', subject: '', tags: [], chapter_refs: [], blocks: [], quality: { warnings: [], warning_hash: 'hash', semantic_review: 'not_checked' } } };
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
describe('serial note autosave', () => {
    const block = (id: string): NoteBlock => ({ block_id: id, type: 'paragraph', data: { markdown: `新内容 ${id}` }, source_ref_ids: ['source'], evidence_ref_ids: ['evidence'], source_alignment: 'aligned', group_id: 'group' });
    const withBlocks = () => ({ ...draft(), content: { ...draft().content!, blocks: ['a', 'b', 'c'].map(block) } });
    it('restores a deleted unpublished block after autosave with its identity, provenance and position', async () => {
        const saver = new DraftAutosaver(withBlocks(), async (revision, content) => ({ ...draft(revision + 1), content: { ...content, quality: draft().content!.quality } }));
        const original = structuredClone(saver.content.blocks[1]);
        saver.deleteBlock(1);
        await saver.flush();
        expect(saver.content.blocks.map(b => b.block_id)).toEqual(['a', 'c']);
        expect(saver.undoDelete()).toBe('b');
        await saver.flush();
        expect(saver.draft.draft_revision).toBe(3);
        expect(saver.content.blocks[1]).toEqual(original);
        expect(saver.deletedCount).toBe(0);
        saver.stopTimer();
    });
    it('serializes undo during an in-flight deletion save without overwriting subsequent text', async () => {
        const pending = deferred<NoteDraft>();
        let writes = 0;
        const saver = new DraftAutosaver(withBlocks(), async (revision, content) => {
            writes++;
            const saved = { ...draft(revision + 1), content: { ...content, quality: draft().content!.quality } };
            if (writes === 1) { await pending.promise; }
            return saved;
        });
        saver.deleteBlock(1);
        const flush = saver.flush();
        saver.change({ ...saver.content, title: '另一个新标题' });
        saver.undoDelete();
        pending.resolve(draft());
        await flush;
        expect(saver.content.title).toBe('另一个新标题');
        expect(saver.content.blocks.map(b => b.block_id)).toEqual(['a', 'b', 'c']);
        expect(writes).toBe(2);
        saver.stopTimer();
    });
    it('undoes consecutive deletes in order, protects the last block and clears recovery on authority reload', async () => {
        const saver = new DraftAutosaver(withBlocks(), async () => withBlocks());
        saver.deleteBlock(1);
        saver.deleteBlock(0);
        expect(saver.deleteBlock(0)).toBe(false);
        saver.undoDelete();
        saver.undoDelete();
        expect(saver.content.blocks.map(b => b.block_id)).toEqual(['a', 'b', 'c']);
        saver.deleteBlock(1);
        saver.reload(withBlocks());
        expect(saver.undoDelete()).toBeUndefined();
        saver.stopTimer();
    });
    it('keeps undo available until space is available at the existing block limit', () => {
        const saver = new DraftAutosaver(withBlocks(), async () => withBlocks());
        saver.deleteBlock(1);
        saver.change({ ...saver.content, blocks: Array.from({ length: 300 }, (_, i) => block(`new-${i}`)) });
        expect(saver.undoDelete()).toBeUndefined();
        expect(saver.deletedCount).toBe(1);
        saver.change({ ...saver.content, blocks: saver.content.blocks.slice(0, 299) });
        expect(saver.undoDelete()).toBe('b');
        expect(saver.content.blocks).toHaveLength(300);
        saver.stopTimer();
    });
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
