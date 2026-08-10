import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink, Loader2, Printer } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { get } from '../api/client';
import { useAuthenticatedBlobUrl } from '../hooks/useAuthenticatedBlobUrl';
import { prepareMathMarkdown } from '../utils/mathText';

type HighlightDetail = {
  metadata?: {
    book_name?: string;
    chapter_title?: string;
    scope_title?: string;
    completed_at?: string;
    updated_at?: string;
    html_path?: string;
    html_url?: string;
  };
  markdown?: string;
  html_url?: string;
  artifacts?: { html_url?: string; html_path?: string; markdown_path?: string };
};

type MarkdownChunk = { id: string; level: number; title: string; markdown: string };

function hashText(value: string): string {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) hash = (hash * 31 + value.charCodeAt(i)) | 0;
  return Math.abs(hash).toString(36);
}

function cleanHeading(raw: string): string {
  return raw
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\$+/g, '')
    .replace(/\s+/g, ' ')
    .trim() || '未命名标题';
}

function splitMarkdown(markdown: string): MarkdownChunk[] {
  const chunks: MarkdownChunk[] = [];
  let current: string[] = [];
  let currentMeta: { id: string; level: number; title: string } | null = null;
  const seen = new Map<string, number>();

  const flush = () => {
    if (!current.length) return;
    chunks.push({
      id: currentMeta?.id || 'intro',
      level: currentMeta?.level || 1,
      title: currentMeta?.title || '概览',
      markdown: current.join('\n').trimEnd(),
    });
    current = [];
  };

  for (const line of markdown.split('\n')) {
    const match = /^(#{1,2})\s+(.+)$/.exec(line.trim());
    if (match) {
      flush();
      const level = match[1].length;
      const title = cleanHeading(match[2]);
      const key = `${level}:${title}`;
      const count = (seen.get(key) || 0) + 1;
      seen.set(key, count);
      currentMeta = { id: `sec-${level}-${hashText(`${key}:${count}`)}`, level, title };
    }
    current.push(line);
  }
  flush();
  return chunks.length ? chunks : [{ id: 'content', level: 1, title: '重点内容', markdown }];
}

const AuthenticatedMarkdownImage = ({ src, alt }: React.ImgHTMLAttributes<HTMLImageElement>) => {
  const source = typeof src === 'string' && src.startsWith('/api/') ? src : '';
  const asset = useAuthenticatedBlobUrl(source);
  if (!source) return <img src={src} alt={alt || ''} />;
  if (asset.loading) return <span className="inline-flex items-center gap-2 text-xs text-text-secondary"><Loader2 className="h-3.5 w-3.5 animate-spin" />正在加载教材图片...</span>;
  if (asset.error) return <span className="text-xs text-red-700">图片加载失败：{asset.error}</span>;
  return asset.url ? <img src={asset.url} alt={alt || ''} /> : null;
};

const MarkdownBlock = ({ markdown }: { markdown: string }) => (
  <div className="markdown-body text-[15px] leading-relaxed break-words">
    <ReactMarkdown components={{ img: AuthenticatedMarkdownImage }} remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false, errorColor: 'inherit' }]]}>
      {prepareMathMarkdown(markdown)}
    </ReactMarkdown>
  </div>
);

const HighlightPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const bookName = searchParams.get('book_name') || '';
  const chapterId = searchParams.get('chapter_id') || '';
  const sectionId = searchParams.get('section_id') || 'all';
  const [detail, setDetail] = useState<HighlightDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      if (!bookName || !chapterId) {
        setError('缺少教材或章节参数。');
        setLoading(false);
        return;
      }
      setLoading(true);
      setError('');
      try {
        const query = sectionId && sectionId !== 'all' ? `?section_id=${encodeURIComponent(sectionId)}` : '';
        const res = await get(`/books/${encodeURIComponent(bookName)}/chapter-highlights/${encodeURIComponent(chapterId)}${query}`, 60000);
        if (!alive) return;
        if (!res?.success) throw new Error(res?.message || '重点尚未生成');
        setDetail(res.data || null);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (alive) setLoading(false);
      }
    };
    load();
    return () => { alive = false; };
  }, [bookName, chapterId, sectionId]);

  const markdown = detail?.markdown || '';
  const chunks = useMemo(() => splitMarkdown(markdown), [markdown]);
  const toc = chunks.filter((chunk) => chunk.level === 2);
  const meta = detail?.metadata || {};
  const title = meta.scope_title || meta.chapter_title || '章节重点';
  const generatedAt = meta.completed_at || meta.updated_at || '';
  const staticHtmlUrl = detail?.artifacts?.html_url || detail?.html_url || meta.html_url || '';
  const staticHtmlAsset = useAuthenticatedBlobUrl(staticHtmlUrl, 'html');
  const localPath = detail?.artifacts?.html_path || meta.html_path || detail?.artifacts?.markdown_path || '';
  const jumpTo = useCallback((id: string) => {
    const target = document.getElementById(id);
    if (!target) return;
    target.scrollIntoView({ block: 'start', behavior: 'auto' });
  }, []);
  return (
    <div ref={scrollRef} className="h-full overflow-y-auto bg-bg-primary px-5 py-5">
      <div className="mx-auto grid max-w-7xl gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="h-fit border border-border bg-bg-card p-4 lg:sticky lg:top-5">
          <div className="mb-3 text-sm font-semibold text-text-primary">目录</div>
          <div className="max-h-[68vh] space-y-1 overflow-y-auto pr-1">
            {toc.length ? toc.map((item) => (
              <button key={item.id} type="button" onClick={() => jumpTo(item.id)} className="block w-full border-l-2 border-transparent py-1.5 pl-2 pr-2 text-left text-xs leading-5 text-text-secondary hover:border-accent hover:bg-[var(--accent-softer)] hover:text-accent">
                {item.title}
              </button>
            )) : <div className="text-xs text-text-secondary">暂无可跳转标题</div>}
          </div>
        </aside>

        <main className="min-w-0">
          <header className="border-b border-border pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="text-xl font-semibold text-text-primary">{title}</h1>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-text-secondary">
                  <span>{bookName}</span>
                  {generatedAt && <span>生成时间 {generatedAt}</span>}
                </div>
                {localPath && <div className="mt-1 break-all text-xs text-text-secondary">本地文件：{localPath}</div>}
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => window.print()} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-bg-card px-3 py-2 text-xs text-text-primary hover:border-accent/50 hover:text-accent">
                  <Printer className="h-3.5 w-3.5" /> 打印
                </button>
                {staticHtmlUrl && <a href={staticHtmlAsset.url || undefined} target="_blank" rel="noreferrer" aria-disabled={!staticHtmlAsset.url} title={staticHtmlAsset.error || undefined} className={`inline-flex items-center gap-1.5 rounded-lg border border-border bg-bg-card px-3 py-2 text-xs text-text-primary hover:border-accent/50 hover:text-accent ${staticHtmlAsset.url ? '' : 'pointer-events-none opacity-55'}`}>{staticHtmlAsset.loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ExternalLink className="h-3.5 w-3.5" />} {staticHtmlAsset.error ? 'HTML 加载失败' : '静态 HTML'}</a>}
              </div>
            </div>
          </header>

          {loading && <div className="mt-8 flex items-center gap-2 text-sm text-text-secondary"><Loader2 className="h-4 w-4 animate-spin" />正在加载本地重点...</div>}
          {!loading && error && <div className="mt-8 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
          {!loading && !error && (
            <article className="mt-5 border border-border bg-bg-card px-5 py-4 shadow-sm">
              {chunks.map((chunk) => (
                <section key={chunk.id} id={chunk.id} className="scroll-mt-5 border-t border-border pt-4 first:border-t-0 first:pt-0" style={{ contentVisibility: 'auto', containIntrinsicSize: '720px' } as React.CSSProperties}>
                  <MarkdownBlock markdown={chunk.markdown} />
                </section>
              ))}
            </article>
          )}
        </main>
      </div>
    </div>
  );
};

export default HighlightPage;
