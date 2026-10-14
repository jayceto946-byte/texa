import { useLocation } from 'react-router-dom';
import { useEffect, useRef, useState, type ReactNode } from 'react';

/** A quotation is inserted into the user's draft; selection never sends a turn. */
export default function AnswerSelection({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const root = useRef<HTMLDivElement>(null);
  const [quote, setQuote] = useState('');
  useEffect(() => {
    const read = () => {
      const selection = window.getSelection();
      const inside = pathname === '/' && selection && !selection.isCollapsed && root.current?.contains(selection.anchorNode) && root.current?.contains(selection.focusNode);
      setQuote(inside ? selection.toString().trim() : '');
    };
    document.addEventListener('selectionchange', read);
    return () => document.removeEventListener('selectionchange', read);
  }, [pathname]);
  return <div ref={root} className="answer-selection">
    {children}
    {quote && <button type="button" className="app-secondary-button answer-quote-button" onMouseDown={event => event.preventDefault()} onClick={() => {
      window.dispatchEvent(new CustomEvent('texa:quote-answer', { detail: { text: quote } }));
      window.getSelection()?.removeAllRanges();
      setQuote('');
    }}>添加到对话</button>}
  </div>;
}
