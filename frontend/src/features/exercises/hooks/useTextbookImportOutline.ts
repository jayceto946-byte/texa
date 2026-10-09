import { useEffect, useState } from 'react';
import { get } from '../../../api/client';

type Section = { title: string; page?: number; level?: number; heading_block_id?: string };
export type TextbookImportChapter = { title: string; page: number; subsections?: Section[] };

export function useTextbookImportOutline(bookName: string) {
  const [state, setState] = useState<{ book: string; chapters: TextbookImportChapter[]; error: string }>({ book: '', chapters: [], error: '' });
  useEffect(() => {
    if (!bookName || bookName === 'default') return;
    let active = true;
    void get(`/books/${encodeURIComponent(bookName)}/chapters`).then((result) => {
      if (active) setState({ book: bookName, chapters: result.data || [], error: result.success ? '' : result.message || '无法读取教材目录' });
    }).catch((error) => {
      if (active) setState({ book: bookName, chapters: [], error: error instanceof Error ? error.message : '无法读取教材目录' });
    });
    return () => { active = false; };
  }, [bookName]);
  return state.book === bookName ? state : { book: bookName, chapters: [], error: '' };
}
