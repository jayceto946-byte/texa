import type { NoteContent, NoteDraft } from './types';
export function editableContent(draft: NoteDraft): NoteContent {
    if (!draft.content)
        throw new Error('草稿尚未完成');
    const { title, abstract, subject, tags, chapter_refs, blocks } = draft.content;
    return { title, abstract, subject, tags, chapter_refs, blocks };
}
export type SaveState = 'saved' | 'dirty' | 'saving' | 'error';
/** Serial CAS writer. A stale response advances the server revision, never local text. */
export class DraftAutosaver {
    draft: NoteDraft;
    content: NoteContent;
    state: SaveState = 'saved';
    error = '';
    closing = false;
    setClosing(value: boolean) { this.closing = value; this.onChange(); }
    private epoch = 0;
    private savedEpoch = 0;
    private pending: Promise<void> | null = null;
    private timer: ReturnType<typeof setTimeout> | null = null;
    onChange: () => void = () => { };
    listen(listener: () => void) { this.onChange = listener; }
    private writer: (revision: number, content: NoteContent) => Promise<NoteDraft>;
    constructor(draft: NoteDraft, writer: (revision: number, content: NoteContent) => Promise<NoteDraft>) {
        this.writer = writer;
        this.draft = draft;
        this.content = editableContent(draft);
    }
    get dirty() { return this.epoch !== this.savedEpoch; }
    reload(draft: NoteDraft) {
        if (this.pending)
            throw new Error('请等待当前草稿保存结束');
        this.stopTimer();
        this.draft = draft;
        this.content = editableContent(draft);
        this.epoch = 0;
        this.savedEpoch = 0;
        this.error = '';
        this.state = 'saved';
        this.onChange();
    }
    change(content: NoteContent) {
        this.content = content;
        this.epoch += 1;
        this.state = 'dirty';
        this.error = '';
        if (this.timer)
            clearTimeout(this.timer);
        this.timer = setTimeout(() => { void this.flush().catch(() => { }); }, 800);
        this.onChange();
    }
    flush(): Promise<void> {
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
        if (this.pending)
            return this.pending;
        const work = async () => {
            while (this.dirty) {
                const epoch = this.epoch;
                const content = structuredClone(this.content);
                this.state = 'saving';
                this.onChange();
                try {
                    const result = await this.writer(this.draft.draft_revision, content);
                    this.draft = result;
                    this.savedEpoch = epoch;
                    if (this.epoch === epoch)
                        this.content = editableContent(result);
                }
                catch (error) {
                    this.state = 'error';
                    this.error = error instanceof Error ? error.message : '草稿保存失败';
                    this.onChange();
                    throw error;
                }
            }
            this.state = 'saved';
            this.error = '';
            this.onChange();
        };
        this.pending = work().finally(() => { this.pending = null; });
        return this.pending;
    }
    stopTimer() { if (this.timer)
        clearTimeout(this.timer); this.timer = null; }
}
// At most one unsaved editor survives a failed navigation. Server is the draft authority.
let retained: {
    id: string;
    editor: DraftAutosaver;
} | null = null;
export function retainedEditor(id: string) { return retained?.id === id ? retained.editor : null; }
export function retainEditor(id: string, editor: DraftAutosaver) {
    if (editor.dirty)
        retained = { id, editor };
    else if (retained?.id === id)
        retained = null;
}
export function unsavedNotePath() { return retained?.editor.dirty ? `/notes/drafts/${retained.id}` : null; }
export async function flushRetainedEditor(aborted = false, freeze = true): Promise<boolean> {
    const editor = retained?.editor;
    if (!editor)
        return true;
    if (aborted) {
        editor.setClosing(false);
        return false;
    }
    if (freeze) editor.setClosing(true);
    try {
        await editor.flush();
        return true;
    }
    catch {
        editor.setClosing(false);
        return false;
    }
}
