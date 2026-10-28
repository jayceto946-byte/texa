import { useEffect, useState } from 'react';
import { get } from '../../../api/client';

type Section = { title: string; page?: number; level?: number; heading_block_id?: string };
export type TextbookImportChapter = { title: string; page: number; subsections?: Section[] };

export function useTextbookImportOutline(bookName: string) {
  const [state, setState] = useState<{ book: string; chapters: TextbookImportChapter[]; error: string }>({ book: '', chapters: [], error: '' });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener('books:changed', refresh);
    return () => window.removeEventListener('books:changed', refresh);
  }, []);
  useEffect(() => {
    if (!bookName || bookName === 'default') return;
    let active = true;
    void get(`/books/${encodeURIComponent(bookName)}/chapters`).then((result) => {
      if (active) setState({ book: bookName, chapters: result.data || [], error: result.success ? '' : result.message || '无法读取教材目录' });
    }).catch((error) => {
      if (active) setState({ book: bookName, chapters: [], error: error instanceof Error ? error.message : '无法读取教材目录' });
    });
    return () => { active = false; };
  }, [bookName, revision]);
  return state.book === bookName ? state : { book: bookName, chapters: [], error: '' };
}
