import { useEffect, useState } from 'react';
import { Image as ImageIcon, Search } from 'lucide-react';
import { get } from '../../api/client';
import type { FigureArtifact } from '../../types';

export default function FigureCatalog({ bookName, onSelect }: { bookName: string; onSelect: (figure: FigureArtifact) => void }) {
  const [items, setItems] = useState<FigureArtifact[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const params = new URLSearchParams({ limit: '100' });
    if (query.trim()) params.set('query', query.trim());
    void get(`/books/${encodeURIComponent(bookName)}/figures?${params.toString()}`, 30000)
      .then((response) => {
        if (!active) return;
        setItems(response?.data?.items || []);
        setTotal(Number(response?.data?.total || 0));
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
  }, [bookName, query]);

  return (
    <div className="figure-catalog">
      <label className="figure-catalog-search">
        <Search className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">搜索图注或章节</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索图注或章节" />
      </label>
      <div className="figure-catalog-summary">{loading ? '正在读取…' : `共 ${total} 幅教材图片`}</div>
      {error && <p className="figure-catalog-error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="figure-catalog-empty">当前 Canonical 教材中没有可用 Figure。重新导入旧教材后才会生成稳定图片资产。</p>
      )}
      <div className="figure-catalog-list">
        {items.map((figure) => (
          <button key={figure.figure_id} type="button" onClick={() => onSelect(figure)} className="figure-catalog-row">
            <ImageIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="figure-catalog-caption">{figure.caption || '无图注 Figure'}</span>
              <span className="figure-catalog-location">
                {figure.page ? `p.${figure.page}` : '未标页'} · {figure.section_path.join(' › ') || '未标章节'}
              </span>
            </span>
          </button>
        ))}
      </div>
      {total > items.length && <p className="figure-catalog-limit">当前显示前 {items.length} 幅，请用搜索缩小范围。</p>}
    </div>
  );
}
