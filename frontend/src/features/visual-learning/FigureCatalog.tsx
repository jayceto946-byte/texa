import { useEffect, useState } from 'react';
import { Image as ImageIcon, Search } from 'lucide-react';
import { get } from '../../api/client';
import type { FigureArtifact } from '../../types';

export default function FigureCatalog({ bookNames = [], onSelect }: { bookNames?: string[]; onSelect: (figure: FigureArtifact) => void }) {
  const [items, setItems] = useState<FigureArtifact[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const params = new URLSearchParams({ limit: '100' });
    if (debouncedQuery.trim()) params.set('query', debouncedQuery.trim());
    const sources = Array.from(new Set(bookNames.map((name) => name.trim()).filter(Boolean)));
    void Promise.allSettled(sources.map((name) => (
      get(`/books/${encodeURIComponent(name)}/figures?${params.toString()}`, 30000)
    )))
      .then((responses) => {
        if (!active) return;
        const available = responses.flatMap((response) => (
          response.status === 'fulfilled' && response.value?.data ? [response.value.data] : []
        ));
        if (!available.length && responses.some((response) => response.status === 'rejected')) {
          const rejected = responses.find((response) => response.status === 'rejected');
          throw rejected?.status === 'rejected' ? rejected.reason : new Error('教材图片读取失败');
        }
        setItems(available.flatMap((result) => result.items || []));
        setTotal(available.reduce((sum, result) => sum + Number(result.total || 0), 0));
      })
      .catch((reason) => {
        if (!active) return;
        setItems([]);
        setTotal(0);
        const message = reason instanceof Error ? reason.message : '';
        if (/canonical document not found/i.test(message)) {
          setError('');
          return;
        }
        setError(message || '教材图片读取失败');
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [bookNames, debouncedQuery]);

  return (
    <div className="figure-catalog">
      <label className="figure-catalog-search">
        <Search className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">搜索图注、章节或邻近正文</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索图注、章节或邻近正文" />
      </label>
      <div className="figure-catalog-summary">{loading ? '正在读取…' : `共 ${total} 幅教材图片`}</div>
      {error && <p className="figure-catalog-error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="figure-catalog-empty">当前教材范围中没有可用 Figure。重新导入旧教材后才会生成稳定图片资产。</p>
      )}
      <div className="figure-catalog-list">
        {items.map((figure) => (
          <button key={figure.figure_id} type="button" onClick={() => onSelect(figure)} className="figure-catalog-row">
            <ImageIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="figure-catalog-caption">{figure.caption || '无图注 Figure'}</span>
              <span className="figure-catalog-location">
                {figure.page ? `p.${figure.page}` : '未标页'} · {figure.section_path.join(' › ') || '未标章节'}
                {figure.match_scope === 'nearby_text' ? ' · 命中邻近正文' : ''}
              </span>
            </span>
          </button>
        ))}
      </div>
      {total > items.length && <p className="figure-catalog-limit">当前显示前 {items.length} 幅，请用搜索缩小范围。</p>}
    </div>
  );
}
