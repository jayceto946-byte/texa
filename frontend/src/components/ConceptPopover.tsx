import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { get } from '../api/client';
import type { ConceptCandidate, ConceptWiki } from '../types';
import { prepareMathMarkdown } from '../utils/mathText';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

interface ConceptPopoverProps {
  concept: ConceptCandidate;
  bookName: string;
}

const ConceptPopover: React.FC<ConceptPopoverProps> = ({ concept, bookName }) => {
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
    <div className="space-y-4 text-sm">
      <div className="border-b border-border pb-3">
        <div className="text-sm font-semibold text-text-primary">{wiki?.concept?.canonical_name || concept.name}</div>
        <div className="mt-1 text-xs text-text-secondary">
          {bookName || '当前教材'}{concept.confidence ? ` · 关联度 ${(concept.confidence * 100).toFixed(0)}%` : ''}
        </div>
      </div>
          {loading && (
            <div className="flex items-center gap-2 text-text-secondary">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在读取概念
            </div>
          )}
          {error && <div className="border-l-2 border-[var(--danger-border)] pl-3 text-[var(--danger)]">{error}</div>}

          {!loading && !error && (
            <>
              <section>
                <h3 className="mb-1 text-xs font-medium text-text-secondary">教材定义</h3>
                <div className="leading-6 text-text-primary">
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false, errorColor: 'inherit' }]]}>
                    {prepareMathMarkdown(wiki?.definition || concept.definition || '暂无定义片段')}
                  </ReactMarkdown>
                </div>
              </section>

              {wiki?.related_formulas?.length ? (
                <section>
                  <h3 className="mb-2 border-t border-border pt-4 text-xs font-medium text-text-secondary">相关公式</h3>
                  <div className="space-y-2">
                    {wiki.related_formulas.slice(0, 3).map((f) => (
                      <div key={f.formula_id} className="overflow-x-auto border-b border-border py-2 last:border-0">
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
  );
};


export default ConceptPopover;
