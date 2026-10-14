import { expect, it } from 'vitest';
import { noteReturnPath } from './navigation';
it('returns only a saved version or draft Notes route', () => {
    const note = `/notes/note_${'a'.repeat(32)}?revision=2`;
    const draft = `/notes/drafts/draft_${'b'.repeat(32)}`;
    expect(noteReturnPath(`?note_path=${encodeURIComponent(note)}`)).toBe(note);
    expect(noteReturnPath(`?note_path=${encodeURIComponent(draft)}`)).toBe(draft);
    for (const path of ['https://example.com', '//example.com', '/settings', `${note}&execute=x`, '/notes/../../settings'])
        expect(noteReturnPath(`?note_path=${encodeURIComponent(path)}`)).toBeNull();
});
