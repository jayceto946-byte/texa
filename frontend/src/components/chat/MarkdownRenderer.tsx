import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import type { PluggableList } from 'unified';
import 'katex/dist/katex.min.css';
import type { ConceptCandidate } from '../../types';
import { useLearningNoteFont } from '../../hooks/useLearningNoteFont';
import { prepareMathMarkdown } from '../../utils/mathText';
import { ErrorBoundary } from '../ErrorBoundary';

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function protectSegments(text: string): { text: string; tokens: string[] } {
  const tokens: string[] = [];
  const protect = (match: string) => {
    const token = `@@PROTECTED_${tokens.length}@@`;
    tokens.push(match);
    return token;
  };
  return {
    text: text
      .replace(/```[\s\S]*?```/g, protect)
      .replace(/\$\$[\s\S]*?\$\$/g, protect)
      .replace(/`[^`]*`/g, protect)
      .replace(/\$(?!\$)(?:\\.|[^$\\])*?\$/g, protect)
      .replace(/\[[^\]\n]{1,240}\]\([^)]+?\)/g, protect),
    tokens,
  };
}

function restoreSegments(text: string, tokens: string[]): string {
  return tokens.reduce((acc, token, index) => acc.replace(`@@PROTECTED_${index}@@`, () => token), text);
}

function linkConcepts(markdown: string, concepts: ConceptCandidate[]): string {
  if (!concepts.length) return markdown;
  const { text, tokens } = protectSegments(markdown);
  let linked = text;
  const usedConcepts = new Set<string>();
  const usedTerms = new Set<string>();

  const terms = concepts
    .flatMap((concept) => [concept.name, ...(concept.aliases || [])].map((term) => ({ term, concept })))
    .filter(({ term }) => term && term.length >= 2)
    .sort((a, b) => b.term.length - a.term.length);

  for (const { term, concept } of terms) {
    if (usedConcepts.has(concept.name) || usedTerms.has(term)) continue;
    const pattern = new RegExp(`(?<![\\]\\[])${escapeRegExp(term)}(?!\\]\\()`, 'u');
    if (!pattern.test(linked)) continue;
    const href = `#concept-${encodeURIComponent(concept.name)}`;
    const token = `@@PROTECTED_${tokens.length}@@`;
    tokens.push(`[${term}](${href})`);
    linked = linked.replace(pattern, token);
    usedConcepts.add(concept.name);
    usedTerms.add(term);
  }

  return restoreSegments(linked, tokens);
}

function countUnescapedDoubleDollars(line: string): number {
  let count = 0;
  for (let i = 0; i < line.length - 1; i += 1) {
    if (line[i] !== '$' || line[i + 1] !== '$') continue;
    let slashCount = 0;
    for (let j = i - 1; j >= 0 && line[j] === '\\'; j -= 1) slashCount += 1;
    if (slashCount % 2 === 0) count += 1;
    i += 1;
  }
  return count;
}

function countUnescapedInlineDollars(line: string): number {
  let count = 0;
  for (let i = 0; i < line.length; i += 1) {
    if (line[i] !== '$') continue;
    if (line[i - 1] === '$' || line[i + 1] === '$') continue;
    let slashCount = 0;
    for (let j = i - 1; j >= 0 && line[j] === '\\'; j -= 1) slashCount += 1;
    if (slashCount % 2 === 0) count += 1;
  }
  return count;
}

function splitMarkdownForRender(markdown: string, maxChars = 10000): string[] {
  if (markdown.length <= maxChars) return [markdown];

  const blocks: string[] = [];
  const current: string[] = [];
  let currentLength = 0;
  let inFence = false;
  let inBlockMath = false;
  let inInlineMath = false;

  const flush = () => {
    const block = current.join('\n').trimEnd();
    if (block) blocks.push(block);
    current.length = 0;
    currentLength = 0;
  };

  for (const line of markdown.split('\n')) {
    const trimmed = line.trim();
    const fenceLine = /^```/.test(trimmed);
    if (fenceLine) inFence = !inFence;

    if (!inFence) {
      const blockMathToggles = countUnescapedDoubleDollars(line);
      if (blockMathToggles % 2 === 1) inBlockMath = !inBlockMath;
      if (!inBlockMath) {
        const inlineMathToggles = countUnescapedInlineDollars(line);
        if (inlineMathToggles % 2 === 1) inInlineMath = !inInlineMath;
      }
    }

    current.push(line);
    currentLength += line.length + 1;

    const canSplit = !inFence && !inBlockMath && !inInlineMath;
    if (canSplit && currentLength >= maxChars && trimmed === '') {
      flush();
    }
  }

  flush();
  return blocks.length ? blocks : [markdown];
}

function blockKey(block: string, index: number): string {
  let hash = 0;
  for (let i = 0; i < block.length; i += 1) {
    hash = (hash * 31 + block.charCodeAt(i)) | 0;
  }
  return `${index}:${block.length}:${hash}`;
}

const PlainMarkdownFallback: React.FC<{ content: string }> = ({ content }) => (
  <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-text-primary">{content}</div>
);

const markdownPlugins: PluggableList = [remarkGfm, remarkMath];
const katexPlugins: PluggableList = [[rehypeKatex, { strict: false, throwOnError: false, errorColor: 'inherit' }]];

const LearningBlockquote = ({ children }: { children?: React.ReactNode }) => {
  useLearningNoteFont();
  return <blockquote className="learning-note my-2 border-l-2 border-border pl-3 text-text-secondary">{children}</blockquote>;
};

export const SimpleMarkdown: React.FC<{ content: string }> = ({ content }) => (
  <div className="markdown-body text-sm leading-relaxed break-words">
    <ReactMarkdown remarkPlugins={markdownPlugins} rehypePlugins={katexPlugins}>
      {prepareMathMarkdown(content || '')}
    </ReactMarkdown>
  </div>
);

export const MarkdownMessage: React.FC<{
  content: string;
  linkedConcepts: ConceptCandidate[];
  onConceptClick: (concept: ConceptCandidate) => void;
}> = ({ content, linkedConcepts, onConceptClick }) => {
  const cleanContent = React.useMemo(() => {
    const withoutRefs = content
      .replace(/\u3010\u6765\u6e90\uff1a(.+?)\u3011/g, '')
      .replace(/\s*\/\s*[a-f0-9]{12,64}(?=\s*\])/gi, '')
      .replace(/\n{3,}/g, '\n\n');
    const mathReady = prepareMathMarkdown(withoutRefs);
    return linkConcepts(mathReady, linkedConcepts);
  }, [content, linkedConcepts]);

  const contentBlocks = React.useMemo(() => splitMarkdownForRender(cleanContent), [cleanContent]);
  const conceptByName = React.useMemo(() => {
    const map = new Map<string, ConceptCandidate>();
    for (const concept of linkedConcepts) map.set(concept.name, concept);
    return map;
  }, [linkedConcepts]);

  const markdownComponents = {
    a({ href, children }: { href?: string; children?: React.ReactNode }) {
      if (href?.startsWith('#concept-')) {
        const name = decodeURIComponent(href.replace('#concept-', ''));
        const concept = conceptByName.get(name);
        return (
          <button
            type="button"
            className="concept-link"
            title="查看知识图谱概念"
            onClick={(e) => {
              e.preventDefault();
              if (concept) onConceptClick(concept);
            }}
          >
            {children}
          </button>
        );
      }
      return (
        <a href={href} className="text-accent underline underline-offset-2" target="_blank" rel="noreferrer">
          {children}
        </a>
      );
    },
    p({ children }: { children?: React.ReactNode }) {
      return <p className="my-1.5">{children}</p>;
    },
    pre({ children }: { children?: React.ReactNode }) {
      return <pre className="my-3 overflow-x-auto rounded-lg border border-border bg-[var(--surface-subtle)] p-3 font-mono text-xs shadow-sm">{children}</pre>;
    },
    code({ className, children, ...props }: { className?: string; children?: React.ReactNode }) {
      const isInline = !className;
      return isInline ? (
        <code className="rounded-md border border-border bg-[var(--accent-softer)] px-1.5 py-0.5 font-mono text-xs text-accent" {...props}>{children}</code>
      ) : (
        <code className={className} {...props}>{children}</code>
      );
    },
    ul({ children }: { children?: React.ReactNode }) {
      return <ul className="list-disc pl-5 my-1.5">{children}</ul>;
    },
    ol({ children }: { children?: React.ReactNode }) {
      return <ol className="list-decimal pl-5 my-1.5">{children}</ol>;
    },
    li({ children }: { children?: React.ReactNode }) {
      return <li className="my-0.5">{children}</li>;
    },
    h1({ children }: { children?: React.ReactNode }) {
      return <h1 className="text-lg font-bold my-2">{children}</h1>;
    },
    h2({ children }: { children?: React.ReactNode }) {
      return <h2 className="text-base font-bold my-2">{children}</h2>;
    },
    h3({ children }: { children?: React.ReactNode }) {
      return <h3 className="text-sm font-bold my-1.5">{children}</h3>;
    },
    blockquote({ children }: { children?: React.ReactNode }) {
      return <LearningBlockquote>{children}</LearningBlockquote>;
    },
    table({ children }: { children?: React.ReactNode }) {
      return <div className="my-2 overflow-x-auto"><table className="border-collapse border border-border text-xs">{children}</table></div>;
    },
    th({ children }: { children?: React.ReactNode }) {
      return <th className="border border-border bg-bg-secondary px-2 py-1">{children}</th>;
    },
    td({ children }: { children?: React.ReactNode }) {
      return <td className="border border-border px-2 py-1">{children}</td>;
    },
  };

  return (
    <div className="markdown-body text-[15px] leading-relaxed break-words">
      {contentBlocks.map((block, index) => {
        const key = blockKey(block, index);
        return (
          <ErrorBoundary key={key} resetKey={key} fallback={<PlainMarkdownFallback content={block} />}>
            <ReactMarkdown remarkPlugins={markdownPlugins} rehypePlugins={katexPlugins} components={markdownComponents}>
              {block}
            </ReactMarkdown>
          </ErrorBoundary>
        );
      })}
    </div>
  );
};