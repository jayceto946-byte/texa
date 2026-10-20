import { useLayoutEffect, useRef } from 'react';

type BlockPosition = { id: string; fraction: number; inset: number };
/** Content anchors are shared by the editor and Markdown; pixel scroll positions are not. */
export function useDraftPosition(editing: boolean) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const focusedBlock = useRef<string | null>(null);
    const pending = useRef<{ block: BlockPosition | null } | null>(null);
    const rememberFocus = (target: EventTarget | null) => {
        if (target instanceof Element) {
            const block = target.closest<HTMLElement>('[data-note-block]');
            if (block) focusedBlock.current = block.dataset.noteBlock || null;
        }
    };
    const capture = () => {
        const scroll = scrollRef.current;
        if (!scroll) return;
        if (scroll.scrollTop <= 1) { pending.current = { block: null }; return; }
        const viewport = scroll.getBoundingClientRect();
        const top = viewport.top + (scroll.querySelector('.note-delete-recovery')?.getBoundingClientRect().height || 0);
        const visible = [...scroll.querySelectorAll<HTMLElement>('[data-note-block]')].filter(el => {
            const r = el.getBoundingClientRect();
            return r.bottom > top && r.top < viewport.bottom;
        });
        const block = visible.find(el => el.dataset.noteBlock === focusedBlock.current) || visible[0];
        if (!block) { pending.current = { block: null }; return; }
        const rect = block.getBoundingClientRect();
        pending.current = { block: { id: block.dataset.noteBlock!, fraction: Math.max(0, (top - rect.top) / rect.height), inset: Math.max(0, rect.top - top) } };
    };
    useLayoutEffect(() => {
        const position = pending.current;
        pending.current = null;
        const scroll = scrollRef.current;
        if (!position || !scroll) return;
        let stopped = false;
        let frame = 0;
        const stop = () => {
            stopped = true;
            cancelAnimationFrame(frame);
            mutations.disconnect();
            resize.disconnect();
            for (const type of ['wheel', 'touchstart', 'pointerdown', 'keydown']) scroll.removeEventListener(type, stop);
        };
        const restore = () => {
            if (stopped) return;
            const block = position.block;
            if (!block) { scroll.scrollTop = 0; return; }
            const target = [...scroll.querySelectorAll<HTMLElement>('[data-note-block]')].find(el => el.dataset.noteBlock === block.id);
            if (!target) return;
            const r = target.getBoundingClientRect();
            const top = scroll.getBoundingClientRect().top + (scroll.querySelector('.note-delete-recovery')?.getBoundingClientRect().height || 0);
            scroll.scrollTop += r.top - top + block.fraction * r.height - Math.min(block.inset, scroll.clientHeight / 2);
        };
        const schedule = () => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => {
                restore();
                // Suspense and MathLive can change preceding block heights after the mode switch.
                const loading = scroll.querySelector('[data-texa-markdown-loading], .note-equation-editor:not(:has(math-field))');
                if (!loading) frame = requestAnimationFrame(() => { restore(); stop(); });
            });
        };
        const mutations = new MutationObserver(schedule);
        const resize = new ResizeObserver(schedule);
        mutations.observe(scroll, { childList: true, subtree: true });
        const document = scroll.querySelector('.note-document');
        if (document) resize.observe(document);
        for (const type of ['wheel', 'touchstart', 'pointerdown', 'keydown']) scroll.addEventListener(type, stop, { passive: true });
        void window.document.fonts.ready.then(() => { if (!stopped) schedule(); });
        schedule();
        return stop;
    }, [editing]);
    return { scrollRef, capture, rememberFocus };
}
