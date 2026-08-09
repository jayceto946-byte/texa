import React, { useMemo, useState } from 'react';
import { Bot, BookOpen, ChevronRight, Globe2, GraduationCap, ShieldAlert, User } from 'lucide-react';
import type { AnswerMode, AssistantSource, ChatAgentCard, ChatChapterHighlightCard, ChatExerciseCard, ChatReportCard, ChatUtilityCard, ConceptCandidate, SubjectRouteSuggestion } from '../types';
import { useChatContext } from '../contexts/ChatContext';
import { displayNumber, groupSourcesByLocation, parseCitations, partitionSources, type SourceChapterGroup } from '../utils/citations';
import ConceptPopover from './ConceptPopover';
import ChapterHighlightCard from './chat/ChapterHighlightCard';
import ExerciseCard from './chat/ExerciseCard';
import { MarkdownMessage } from './chat/MarkdownMessage';
import MistakeQuickCaptureCard from './chat/MistakeQuickCaptureCard';
import ReportCard from './chat/ReportCard';
import AgentResultCard from './chat/AgentResultCard';
import SubjectRouteSuggestionCard from './chat/SubjectRouteSuggestionCard';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  variant?: 'message' | 'document';
  stage?: string;
  linkedConcepts?: ConceptCandidate[];
  sources?: AssistantSource[];
  sourceChapters?: string[];
  turnId?: string;
  subjectSuggestion?: SubjectRouteSuggestion;
  answerMode?: AnswerMode;
  suggestedAnswerMode?: AnswerMode;
  scopeReason?: string;
  originalQuestion?: string;
  onRequestGlobalAnswer?: (question: string) => void;
  onRequestSuggestedAnswer?: (question: string, mode: AnswerMode) => void;
  reportCard?: ChatReportCard;
  exerciseCard?: ChatExerciseCard;
  chapterHighlightCard?: ChatChapterHighlightCard;
  utilityCard?: ChatUtilityCard;
  agentCard?: ChatAgentCard;
}

const SourceGroupList: React.FC<{ groups: SourceChapterGroup[]; cited: boolean }> = ({ groups, cited }) => (
  <div className="space-y-2.5">
    {groups.map((group) => (
      <section key={group.key}>
        <div className="mb-1 text-[11px] font-semibold leading-5 text-text-primary">
          {group.bookName} · {group.chapter}
        </div>
        <ul className="space-y-1 border-l border-border pl-2.5">
          {group.locations.map((location) => {
            const path = location.path[0] === group.chapter ? location.path.slice(1) : location.path;
            const locationText = path.length > 0
              ? path.join(' › ')
              : location.fallbackLabel || '章级概述';
            const numberText = location.citationNumbers.map(displayNumber).join('');
            const pageText = location.pageIdx >= 0 ? ` · p.${location.pageIdx + 1}` : '';
            const mergedText = location.sources.length > 1 ? ` · 合并 ${location.sources.length} 段` : '';
            return (
              <li key={location.key} className="flex gap-1.5 text-xs leading-relaxed text-text-secondary">
                <span className={`shrink-0 select-none ${cited ? 'text-accent' : 'text-text-tertiary'}`}>
                  {cited ? numberText : '·'}
                </span>
                <span className="min-w-0">{locationText}{pageText}{mergedText}</span>
              </li>
            );
          })}
        </ul>
      </section>
    ))}
  </div>
);

const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, variant = 'message', stage, turnId, subjectSuggestion, answerMode, suggestedAnswerMode, scopeReason, originalQuestion, onRequestGlobalAnswer, onRequestSuggestedAnswer, linkedConcepts = [], sources = [], sourceChapters = [], reportCard, exerciseCard, chapterHighlightCard, utilityCard, agentCard }) => {
  const [showSources, setShowSources] = useState(false);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [referencesExpanded, setReferencesExpanded] = useState(false);
  const [activeConcept, setActiveConcept] = useState<ConceptCandidate | null>(null);
  const [scopeResolved, setScopeResolved] = useState(false);
  const sourcesRef = React.useRef<HTMLDivElement | null>(null);
  const referencesRef = React.useRef<HTMLDivElement | null>(null);
  const chapterRef = React.useRef<HTMLDivElement | null>(null);
  const { bookName, subject } = useChatContext();

  const references = useMemo(() => {
    if (role !== 'assistant') return [];
    const matches: string[] = [];
    const regex = /【来源：(.+?)】/g;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(content)) !== null) {
      matches.push(match[1]);
    }
    return matches;
  }, [content, role]);

  const hasStructuredSources = sources.length > 0;

  const validIds = useMemo(() => {
    const ids = new Set<string>();
    for (const src of sources) {
      if (src.id) ids.add(src.id);
    }
    return ids;
  }, [sources]);

  // 编号由正文首次引用顺序派生；validIds 为空时视为全部合法（流式阶段尚未拿到 sources）。
  const { order: citationOrder } = useMemo(() => parseCitations(content, validIds), [content, validIds]);
  const { cited: citedSources, references: referenceSources } = useMemo(
    () => partitionSources(sources, citationOrder),
    [sources, citationOrder],
  );
  const citedSourceGroups = useMemo(
    () => groupSourcesByLocation(citedSources, citationOrder),
    [citedSources, citationOrder],
  );
  const referenceSourceGroups = useMemo(
    () => groupSourcesByLocation(referenceSources),
    [referenceSources],
  );

  const scrollToSources = () => {
    if (hasStructuredSources) {
      // 一次操作直接看到来源内容：先展开，再滚动到来源区
      setSourcesExpanded(true);
      requestAnimationFrame(() => sourcesRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    } else if (references.length > 0) {
      setShowSources(true);
      requestAnimationFrame(() => referencesRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
    } else if (sourceChapters.length > 0) {
      chapterRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  const isUser = role === 'user';
  const isThinking = !isUser && (stage === 'thinking' || stage === 'plan') && !content.trim();
  const hasCard = Boolean(reportCard || exerciseCard || chapterHighlightCard || utilityCard || agentCard);
  const showMessageTools = !hasCard && !isThinking;
  const modeLabel = answerMode === 'textbook_grounded'
    ? '教材依据'
    : answerMode === 'subject_general'
      ? '学科通用'
      : answerMode === 'global_general'
        ? '跨学科通用'
        : answerMode === 'subject_mismatch'
          ? '范围待确认'
          : '';
  const ModeIcon = answerMode === 'textbook_grounded'
    ? BookOpen
    : answerMode === 'subject_general'
      ? GraduationCap
      : answerMode === 'subject_mismatch'
        ? ShieldAlert
        : Globe2;

  return (
    <div className={variant === 'document' ? 'min-w-0' : `mb-5 flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={variant === 'document' ? 'min-w-0 text-text-primary' : `max-w-[min(96%,820px)] rounded-2xl px-3 py-3 sm:max-w-[min(86%,820px)] sm:px-4 ${isUser ? 'bg-accent text-white' : 'border border-border bg-bg-card text-text-primary'}`}>
        {variant === 'message' && (
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4 text-accent" />}
              <span className="text-xs opacity-70">{isUser ? '你' : 'AI 助手'}</span>
              {!isUser && stage === 'done' && modeLabel && (
                <span
                  title={scopeReason || modeLabel}
                  className={`inline-flex items-center gap-1 rounded-full bg-[var(--surface-subtle)] px-2 py-0.5 text-[10px] font-medium ${answerMode === 'subject_mismatch' ? 'text-[var(--danger)]' : 'text-text-secondary'}`}
                >
                  <ModeIcon className="h-3 w-3" />
                  {modeLabel}
                </span>
              )}
            </div>
            {!isUser && (hasStructuredSources || references.length > 0 || sourceChapters.length > 0) && (
              <button
                type="button"
                onClick={scrollToSources}
                title="滚动到参考来源"
                className="flex items-center gap-1 text-xs text-text-secondary/60 transition-colors hover:text-text-secondary"
              >
                <BookOpen className="h-3 w-3" />
                来源 {hasStructuredSources ? sources.length : references.length || sourceChapters.length}
              </button>
            )}
          </div>
        )}

        {agentCard ? (
          <AgentResultCard card={agentCard} />
        ) : reportCard ? (
          <ReportCard card={reportCard} />
        ) : chapterHighlightCard ? (
          <ChapterHighlightCard card={chapterHighlightCard} />
        ) : exerciseCard ? (
          <ExerciseCard card={exerciseCard} bookName={bookName} />
        ) : utilityCard?.kind === 'mistake_quick_capture' ? (
          <MistakeQuickCaptureCard bookName={bookName} subject={subject} />
        ) : isThinking ? (
          <div className="flex items-center gap-2 py-2 text-text-secondary">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-accent" />
            <span className="text-sm">思考中...</span>
          </div>
        ) : (
          <MarkdownMessage content={content} linkedConcepts={isUser ? [] : linkedConcepts} onConceptClick={setActiveConcept} citationIds={validIds} />
        )}

        {!isUser && stage === 'done' && answerMode === 'subject_mismatch' && originalQuestion && onRequestGlobalAnswer && !scopeResolved && (
          <div className="mt-3 rounded-lg border border-accent/25 bg-[var(--accent-softer)] px-3 py-2">
            <div className="text-xs leading-5 text-text-secondary">这次回答尚未进入当前学科记忆。</div>
            <button
              type="button"
              onClick={() => {
                setScopeResolved(true);
                onRequestGlobalAnswer(originalQuestion);
              }}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white"
            >
              <Globe2 className="h-3.5 w-3.5" />
              跨学科通用回答
            </button>
          </div>
        )}

        {!isUser && stage === 'done' && answerMode === 'textbook_grounded' && suggestedAnswerMode && originalQuestion && onRequestSuggestedAnswer && !scopeResolved && (
          <div className="mt-3 rounded-lg border border-accent/25 bg-[var(--accent-softer)] px-3 py-2">
            <div className="text-xs leading-5 text-text-secondary">教材证据不足时不会自动混入模型知识；你可以显式放宽本题的回答来源。</div>
            <button
              type="button"
              onClick={() => {
                setScopeResolved(true);
                onRequestSuggestedAnswer(originalQuestion, suggestedAnswerMode);
              }}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white"
            >
              {suggestedAnswerMode === 'subject_general' ? <GraduationCap className="h-3.5 w-3.5" /> : <Globe2 className="h-3.5 w-3.5" />}
              {suggestedAnswerMode === 'subject_general' ? '改用学科通用回答' : '改用跨学科通用回答'}
            </button>
          </div>
        )}

        {hasStructuredSources && (
          <div ref={sourcesRef} className="mt-3 rounded-lg border border-border bg-[var(--surface-subtle)] px-3 py-2">
            <button
              type="button"
              onClick={() => setSourcesExpanded((v) => !v)}
              aria-expanded={sourcesExpanded}
              className="flex w-full cursor-pointer items-center gap-1.5 text-left text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
            >
              <BookOpen className="h-3 w-3" />
              <span className="flex-1">
                {citedSources.length > 0 ? `参考来源 ${citedSources.length} 条` : `参考材料 ${referenceSources.length} 条`}
              </span>
              <ChevronRight className={`h-3.5 w-3.5 shrink-0 transition-transform duration-200 ${sourcesExpanded ? 'rotate-90' : ''}`} />
            </button>
            {sourcesExpanded && (
              <div className="mt-1.5">
                {citedSources.length > 0 ? (
                  <>
                    <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-text-secondary">
                      <BookOpen className="h-3 w-3" />
                      参考来源
                    </div>
                    <SourceGroupList groups={citedSourceGroups} cited />
                  </>
                ) : (
                  <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-text-secondary">
                    <BookOpen className="h-3 w-3" />
                    参考材料
                  </div>
                )}
                {referenceSources.length > 0 && (
                  <>
                    {citedSources.length > 0 ? (
                      <button
                        type="button"
                        onClick={() => setReferencesExpanded((value) => !value)}
                        aria-expanded={referencesExpanded}
                        className="mt-2 flex w-full items-center gap-1 text-left text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
                      >
                        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${referencesExpanded ? 'rotate-90' : ''}`} />
                        其他检索材料 {referenceSources.length} 条
                      </button>
                    ) : null}
                    {(citedSources.length === 0 || referencesExpanded) && (
                      <div className={citedSources.length > 0 ? 'mt-1.5' : ''}>
                        <SourceGroupList groups={referenceSourceGroups} cited={false} />
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {!hasStructuredSources && !isUser && sourceChapters.length > 0 && (
          <div ref={chapterRef} className="mt-3 border-t border-border pt-2 text-xs text-text-secondary/70">
            参考章节：{sourceChapters.join('、')}
          </div>
        )}

        {!isUser && stage === 'done' && subjectSuggestion && (
          <SubjectRouteSuggestionCard suggestion={subjectSuggestion} turnId={turnId} />
        )}

        {showMessageTools && linkedConcepts.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5 border-t border-border pt-3">
            {linkedConcepts.slice(0, 8).map((concept) => (
              <button
                key={concept.concept_id || concept.name}
                type="button"
                onClick={() => setActiveConcept(concept)}
                className="rounded-full border border-accent/20 bg-[var(--accent-softer)] px-2.5 py-1 text-xs text-accent transition-colors hover:border-accent/50"
              >
                {concept.name}
              </button>
            ))}
          </div>
        )}

        {showMessageTools && !hasStructuredSources && references.length > 0 && (
          <div ref={referencesRef} className="mt-3 border-t border-border pt-2">
            <button onClick={() => setShowSources(!showSources)} className="flex items-center gap-1 text-xs text-text-secondary transition-colors hover:text-text-primary">
              <BookOpen className="h-3 w-3" />
              {showSources ? '隐藏来源' : `查看来源 (${references.length})`}
            </button>
            {showSources && (
              <div className="mt-2 space-y-1">
                {references.map((ref, idx) => (
                  <div key={idx} className="rounded-lg border border-border bg-[var(--surface-subtle)] px-2 py-1 text-xs text-text-secondary">
                    {ref}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      {activeConcept && <ConceptPopover concept={activeConcept} bookName={bookName} onClose={() => setActiveConcept(null)} />}
    </div>
  );
};

export default ChatMessage;
