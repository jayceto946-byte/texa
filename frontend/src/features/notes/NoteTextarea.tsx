import { useLayoutEffect, useRef } from 'react';
import type { TextareaHTMLAttributes } from 'react';

/** Grow prose with its content; CSS bounds very long blocks instead of all paragraphs. */
export function NoteTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
    const ref = useRef<HTMLTextAreaElement>(null);
    useLayoutEffect(() => {
        const field = ref.current;
        if (!field) return;
        const fit = () => {
            const c = getComputedStyle(field);
            field.style.height = '0px';
            field.style.height = `${field.scrollHeight + parseFloat(c.borderTopWidth) + parseFloat(c.borderBottomWidth)}px`;
        };
        fit();
        let width = field.getBoundingClientRect().width;
        const resize = new ResizeObserver(() => {
            const next = field.getBoundingClientRect().width;
            if (next !== width) { width = next; fit(); }
        });
        resize.observe(field);
        let mounted = true;
        void document.fonts.ready.then(() => { if (mounted) fit(); });
        return () => { mounted = false; resize.disconnect(); };
    }, [props.value]);
    return <textarea {...props} ref={ref} rows={1} className={`note-autosize ${props.className || ''}`} />;
}
