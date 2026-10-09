import React, { lazy, Suspense } from 'react';
import type { ConceptCandidate } from '../../types';

type SimpleMarkdownProps = { content: string };
type MarkdownMessageProps = {
  content: string;
  linkedConcepts?: ConceptCandidate[];
  onConceptClick?: (concept: ConceptCandidate) => void;
  citationIds?: Set<string>;
  disableRemoteMedia?: boolean;
};

const SimpleMarkdownRenderer = lazy(() =>
  import('./MarkdownRenderer').then((module) => ({ default: module.SimpleMarkdown })),
);

const MarkdownRenderer = lazy(() =>
  import('./MarkdownRenderer').then((module) => ({ default: module.MarkdownMessage })),
);

const MarkdownLoadingFallback: React.FC = () => (
  <div aria-busy="true" className="min-h-6 text-xs leading-relaxed text-text-secondary">正在加载内容…</div>
);

export const SimpleMarkdown: React.FC<SimpleMarkdownProps> = ({ content }) => (
  <Suspense fallback={<MarkdownLoadingFallback />}>
    <SimpleMarkdownRenderer content={content} />
  </Suspense>
);

export const MarkdownMessage: React.FC<MarkdownMessageProps> = React.memo(({ content, linkedConcepts = [], onConceptClick = () => undefined, citationIds, disableRemoteMedia }: MarkdownMessageProps) => (
  <Suspense fallback={<MarkdownLoadingFallback />}>
    <MarkdownRenderer content={content} linkedConcepts={linkedConcepts} onConceptClick={onConceptClick} citationIds={citationIds} disableRemoteMedia={disableRemoteMedia} />
  </Suspense>
), (previous, next) => previous.content === next.content
  && (previous.linkedConcepts === next.linkedConcepts || (!previous.linkedConcepts?.length && !next.linkedConcepts?.length))
  && previous.onConceptClick === next.onConceptClick
  && previous.disableRemoteMedia === next.disableRemoteMedia
  && (previous.citationIds === next.citationIds || Boolean(previous.citationIds && next.citationIds
    && previous.citationIds.size === next.citationIds.size
    && [...previous.citationIds].every(id => next.citationIds!.has(id)))));
