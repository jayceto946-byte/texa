/** Only Notes routes can be used as the return destination of a source jump. */
export function noteReturnPath(search: string): string | null {
    const path = new URLSearchParams(search).get('note_path');
    return path && /^\/notes\/(?:drafts\/draft_[a-f0-9]{32}|note_[a-f0-9]{32}(?:\?revision=[1-9]\d*)?)$/.test(path) ? path : null;
}
