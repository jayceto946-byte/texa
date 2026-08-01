import { useEffect } from 'react';
import noteFontCssUrl from 'lxgw-wenkai-screen-web/lxgwwenkaiscreen/result.css?url';

const NOTE_FONT_STYLESHEET_ID = 'lxgw-wenkai-screen-stylesheet';

export function useLearningNoteFont() {
  useEffect(() => {
    if (document.getElementById(NOTE_FONT_STYLESHEET_ID)) return;
    const link = document.createElement('link');
    link.id = NOTE_FONT_STYLESHEET_ID;
    link.rel = 'stylesheet';
    link.href = noteFontCssUrl;
    document.head.appendChild(link);
  }, []);
}