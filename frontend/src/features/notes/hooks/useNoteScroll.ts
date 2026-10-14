import { useEffect, useRef } from 'react';
// Reading positions only; no document bodies or authoritative drafts are cached here.
const positions = new Map<string, number>();
export function useNoteScroll(key: string, ready: boolean) {
    const ref = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (ready && ref.current) ref.current.scrollTop = positions.get(key) || 0;
    }, [key, ready]);
    const remember = () => {
        if (!ref.current) return;
        positions.delete(key);
        positions.set(key, ref.current.scrollTop);
        if (positions.size > 20) positions.delete(positions.keys().next().value!);
    };
    return { ref, onScroll: remember };
}
