import React, { useEffect, useState } from 'react';
import { BookOpen, Loader2 } from 'lucide-react';
import { get } from '../api/client';
import type { ConceptCandidate, ConceptWiki } from '../types';
import { prepareMathMarkdown } from '../utils/mathText';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

interface ConceptPopoverProps {
  concept: ConceptCandidate;
  bookName: string;
  onClose: () => void;
}

const ConceptPopover: React.FC<ConceptPopoverProps> = ({ concept, bookName, onClose }) => {
  const [wiki, setWiki] = useState<ConceptWiki | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!bookName || !concept.name) return;
      setLoading(true);
      setError('');
      try {
        const res = await get(
          `/kg/concept-wiki?book_name=${encodeURIComponent(bookName)}&name=${encodeURIComponent(concept.name)}`
        );
        if (!cancelled) {
          if (res?.success) setWiki(res.data);
          else setError(res?.message || '未找到概念');
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [bookName, concept.name]);


  return (
    <div className="fixed inset-0 z-40" onClick={onClose}>
      <div className="app-overlay-enter absolute inset-0 bg-black/20" />
      <div
        className="app-popover-enter absolute right-6 top-20 w-[min(420px,calc(100vw-2rem))] max-h-[75vh] overflow-y-auto rounded-lg border border-border bg-bg-secondary"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
              <BookOpen className="h-4 w-4 text-accent" />
              {wiki?.concept?.canonical_name || concept.name}
            </div>
            <div className="mt-1 text-xs text-text-secondary">
              {concept.confidence ? `置信度 ${(concept.confidence * 100).toFixed(0)}%` : '概念索引'}
            </div>
          </div>
          <button className="text-text-secondary hover:text-text-primary" onClick={onClose}>×</button>
        </div>

        <div className="space-y-4 px-4 py-3 text-sm">
          {loading && (
            <div className="flex items-center gap-2 text-text-secondary">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载概念卡片...
            </div>
          )}
          {error && <div className="rounded border border-red-300 bg-red-50 p-2 text-[var(--danger)]">{error}</div>}

          {!loading && !error && (
            <>
              <section>
                <h3 className="mb-1 text-xs font-medium text-text-secondary">教材定义</h3>
                <div className="rounded border border-border bg-bg-primary p-3 text-text-primary">
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false, errorColor: 'inherit' }]]}>
                    {prepareMathMarkdown(wiki?.definition || concept.definition || '暂无定义片段')}
                  </ReactMarkdown>
                </div>
              </section>

              {wiki?.related_formulas?.length ? (
                <section>
                  <h3 className="mb-2 text-xs font-medium text-text-secondary">相关公式</h3>
                  <div className="space-y-2">
                    {wiki.related_formulas.slice(0, 3).map((f) => (
                      <div key={f.formula_id} className="rounded border border-border bg-bg-primary p-2">
                        <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false, errorColor: 'inherit' }]]}>
                          {prepareMathMarkdown(`$$${f.formula_latex}$$`)}
                        </ReactMarkdown>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
};


export default ConceptPopover;
