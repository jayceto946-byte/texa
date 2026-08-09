import React, { lazy, Suspense } from 'react';
import type { ConceptCandidate } from '../../types';

type SimpleMarkdownProps = { content: string };
type MarkdownMessageProps = {
  content: string;
  linkedConcepts?: ConceptCandidate[];
  onConceptClick?: (concept: ConceptCandidate) => void;
  citationIds?: Set<string>;
};

const SimpleMarkdownRenderer = lazy(() =>
  import('./MarkdownRenderer').then((module) => ({ default: module.SimpleMarkdown })),
);

const MarkdownRenderer = lazy(() =>
  import('./MarkdownRenderer').then((module) => ({ default: module.MarkdownMessage })),
);

const PlainMarkdownFallback: React.FC<SimpleMarkdownProps> = ({ content }) => (
  <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-text-primary">{content}</div>
);

export const SimpleMarkdown: React.FC<SimpleMarkdownProps> = ({ content }) => (
  <Suspense fallback={<PlainMarkdownFallback content={content} />}>
    <SimpleMarkdownRenderer content={content} />
  </Suspense>
);

export const MarkdownMessage: React.FC<MarkdownMessageProps> = ({ content, linkedConcepts = [], onConceptClick = () => undefined, citationIds }) => (
  <Suspense fallback={<PlainMarkdownFallback content={content} />}>
    <MarkdownRenderer content={content} linkedConcepts={linkedConcepts} onConceptClick={onConceptClick} citationIds={citationIds} />
  </Suspense>
);
