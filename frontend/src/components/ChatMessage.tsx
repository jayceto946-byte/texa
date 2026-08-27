import React, { useMemo, useState } from 'react';
import { BookOpen, Globe2, GraduationCap, Paperclip, ShieldAlert, ThumbsDown, ThumbsUp } from 'lucide-react';
import type { AnswerMode, AssistantSource, ChatActivity, ChatAgentCard, ChatChapterHighlightCard, ChatExerciseCard, ChatReportCard, ChatUtilityCard, ConceptCandidate, LearningTaskState, SubjectRouteSuggestion } from '../types';
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
import { post } from '../api/client';
import ExecutionTrace from './chat/ExecutionTrace';
import LearningTaskGate from './chat/LearningTaskGate';
import LearningTaskActions from './chat/LearningTaskActions';
import LearningTaskResume from './chat/LearningTaskResume';
import { useInspector } from '../contexts/InspectorContext';
import { useAuthenticatedBlobUrl } from '../hooks/useAuthenticatedBlobUrl';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  messageId?: string;
  answerFeedback?: { rating: 'helpful' | 'unhelpful'; reasons?: string[]; updated_at?: string };
  variant?: 'message' | 'document';
  stage?: string;
  activities?: ChatActivity[];
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
  learningTask?: LearningTaskState;
  onResumeLearningTask?: (task: LearningTaskState, action: 'provide_input' | 'method_only', file?: File) => Promise<void> | void;
  onResumeInterruptedTask?: (task: LearningTaskState) => void;
}

function splitQuestionAttachment(content: string) {
  const match = content.match(/^📎\s*([^\r\n]+)\r?\n(?:\r?\n)+([\s\S]*)$/);
  return match ? { attachmentName: match[1].trim(), body: match[2] } : { attachmentName: '', body: content };
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

const FigureSourceDetail = ({ source }: { source: AssistantSource }) => {
  const [showPdf, setShowPdf] = useState(false);
  const image = useAuthenticatedBlobUrl(source.asset_url || '');
  const pdf = useAuthenticatedBlobUrl(showPdf ? source.pdf_url || '' : '');
  return (
    <section className="figure-source-inspector">
      <div className="figure-source-inspector-heading">
        <div>
          <h3>{source.caption || source.label || '教材 Figure'}</h3>
          <p>{typeof source.page_idx === 'number' && source.page_idx >= 0 ? `p.${source.page_idx + 1}` : '未标页'} · {(source.section_path || []).join(' › ') || source.book_name}</p>
        </div>
        {source.pdf_url && <button type="button" onClick={() => setShowPdf((value) => !value)}>{showPdf ? '收起教材页' : '打开教材页'}</button>}
      </div>
      {image.loading && <div className="figure-source-status">正在读取 Figure…</div>}
      {image.error && <div className="figure-source-status is-error">{image.error}</div>}
      {image.url && <img src={image.url} alt={source.caption || source.label || '教材 Figure'} />}
      {showPdf && pdf.loading && <div className="figure-source-status">正在读取教材 PDF…</div>}
      {showPdf && pdf.error && <div className="figure-source-status is-error">{pdf.error}</div>}
      {showPdf && pdf.url && <iframe title="教材 PDF 来源页" src={`${pdf.url}#page=${Math.max(1, Number(source.page_idx ?? 0) + 1)}`} />}
    </section>
  );
};

const SourceInspectorContent = ({ citedGroups, referenceGroups, chapters, legacyReferences, figureSources }: { citedGroups: SourceChapterGroup[]; referenceGroups: SourceChapterGroup[]; chapters: string[]; legacyReferences: string[]; figureSources: AssistantSource[] }) => (
  <div className="space-y-5">
    {figureSources.map((source) => <FigureSourceDetail key={source.figure_id || source.id} source={source} />)}
    {citedGroups.length > 0 && (
      <section>
        <h3 className="mb-2 text-xs font-semibold text-text-primary">正文引用</h3>
        <SourceGroupList groups={citedGroups} cited />
      </section>
    )}
    {referenceGroups.length > 0 && (
      <section className={citedGroups.length > 0 ? 'border-t border-border pt-4' : ''}>
        <h3 className="mb-2 text-xs font-semibold text-text-primary">其他检索材料</h3>
        <SourceGroupList groups={referenceGroups} cited={false} />
      </section>
    )}
    {chapters.length > 0 && (
      <section className="border-t border-border pt-4">
        <h3 className="mb-2 text-xs font-semibold text-text-primary">参考章节</h3>
        <div className="space-y-1 text-xs leading-5 text-text-secondary">{chapters.map((chapter) => <div key={chapter}>{chapter}</div>)}</div>
      </section>
    )}
    {legacyReferences.length > 0 && (
      <section className="border-t border-border pt-4">
        <h3 className="mb-2 text-xs font-semibold text-text-primary">来源标记</h3>
        <div className="space-y-2 text-xs leading-5 text-text-secondary">{legacyReferences.map((reference, index) => <div key={`${reference}-${index}`}>{reference}</div>)}</div>
      </section>
    )}
  </div>
);

const feedbackReasons = [
  ['wrong_object', '答错对象'],
  ['forgot_context', '忘记前文条件'],
  ['stale_evidence', '错用旧证据'],
  ['insufficient_evidence', '教材依据不足'],
  ['irrelevant_or_repetitive', '答非所问或重复'],
] as const;

const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, messageId, answerFeedback, variant = 'message', stage, activities = [], turnId, subjectSuggestion, answerMode, suggestedAnswerMode, scopeReason, originalQuestion, onRequestGlobalAnswer, onRequestSuggestedAnswer, linkedConcepts = [], sources = [], sourceChapters = [], reportCard, exerciseCard, chapterHighlightCard, utilityCard, agentCard, learningTask, onResumeLearningTask, onResumeInterruptedTask }) => {
  const [scopeResolved, setScopeResolved] = useState(false);
  const [feedback, setFeedback] = useState(answerFeedback);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [showFeedbackReasons, setShowFeedbackReasons] = useState(false);
  const [feedbackError, setFeedbackError] = useState('');
  const { bookName, subject, conversationId } = useChatContext();
  const { openInspector } = useInspector();

  const submitFeedback = async (rating: 'helpful' | 'unhelpful', reasons: string[] = []) => {
    if (!messageId || feedbackBusy) return;
    setFeedbackBusy(true);
    setFeedbackError('');
    try {
      const result = await post('/chat/feedback', {
        conversation_id: conversationId,
        message_id: messageId,
        rating,
        reasons,
      });
      if (!result?.success) throw new Error(result?.message || '反馈保存失败');
      setFeedback({ rating, reasons });
      setShowFeedbackReasons(false);
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : '反馈保存失败');
    } finally {
      setFeedbackBusy(false);
    }
  };

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
    () => groupSourcesByLocation(citedSources.filter((source) => !source.figure_id), citationOrder),
    [citedSources, citationOrder],
  );
  const referenceSourceGroups = useMemo(
    () => groupSourcesByLocation(referenceSources.filter((source) => !source.figure_id)),
    [referenceSources],
  );

  const openSources = () => {
    openInspector({
      kind: 'source',
      title: '回答来源',
      subtitle: bookName || subject || '当前学习范围',
      content: <SourceInspectorContent citedGroups={citedSourceGroups} referenceGroups={referenceSourceGroups} chapters={sourceChapters} legacyReferences={references} figureSources={sources.filter((source) => Boolean(source.figure_id))} />,
    });
  };

  const openConcept = (concept: ConceptCandidate) => {
    openInspector({
      kind: 'concept',
      title: concept.name,
      subtitle: '概念',
      content: <ConceptPopover concept={concept} bookName={bookName} />,
    });
  };

  const isUser = role === 'user';
  const questionContent = useMemo(
    () => (isUser && variant === 'message' ? splitQuestionAttachment(content) : { attachmentName: '', body: content }),
    [content, isUser, variant],
  );
  const isThinking = !isUser && (
    stage === 'agent'
    || ((stage === 'thinking' || stage === 'plan') && !content.trim())
  );
  const hasCard = Boolean(reportCard || exerciseCard || chapterHighlightCard || utilityCard || agentCard);
  const showMessageTools = !hasCard && !isThinking;
  const modeLabel = answerMode === 'textbook_grounded'
    ? '教材依据'
    : answerMode === 'visual_grounded'
      ? '教材图片依据'
    : answerMode === 'subject_general'
      ? '学科通用'
      : answerMode === 'global_general'
        ? '跨学科通用'
        : answerMode === 'subject_mismatch'
          ? '范围待确认'
          : '';
  const ModeIcon = answerMode === 'textbook_grounded'
    ? BookOpen
    : answerMode === 'visual_grounded'
      ? BookOpen
    : answerMode === 'subject_general'
      ? GraduationCap
      : answerMode === 'subject_mismatch'
        ? ShieldAlert
        : Globe2;

  return (
    <div className={variant === 'document' ? 'min-w-0' : `learning-message ${isUser ? 'is-question' : 'is-answer'}`}>
      <article className={variant === 'document' ? 'min-w-0 text-text-primary' : isUser ? 'learning-question' : 'learning-answer-document'}>
        {variant === 'message' && (
          <div className="learning-message-header">
            <div className="flex items-center gap-2 text-xs text-text-secondary">
              <span>{isUser ? '问题' : '回答'}</span>
              {!isUser && stage === 'done' && modeLabel && (
                <span
                  title={scopeReason || modeLabel}
                  className={`inline-flex items-center gap-1 border-l border-border pl-2 text-[11px] ${answerMode === 'subject_mismatch' ? 'text-[var(--danger)]' : 'text-text-secondary'}`}
                >
                  <ModeIcon className="h-3 w-3" />
                  {modeLabel}
                </span>
              )}
            </div>
            {!isUser && (hasStructuredSources || references.length > 0 || sourceChapters.length > 0) && (
              <button
                type="button"
                onClick={openSources}
                title="检查回答来源"
                className="flex items-center gap-1 text-xs text-text-secondary transition-colors hover:text-accent"
              >
                <BookOpen className="h-3 w-3" />
                来源 {hasStructuredSources ? sources.length : references.length || sourceChapters.length}
              </button>
            )}
          </div>
        )}

        {isUser && questionContent.attachmentName && (
          <div className="learning-query-attachment">
            <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
            <span>附件：{questionContent.attachmentName}</span>
          </div>
        )}

        {!isUser && activities.length > 0 && <ExecutionTrace activities={activities} stage={stage} />}

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
        ) : isThinking && activities.length === 0 ? (
          <div className="flex items-center gap-2 py-2 text-text-secondary">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-accent" />
            <span className="text-sm">{stage === 'agent' ? content || '正在调用学习工具…' : '思考中...'}</span>
          </div>
        ) : content.trim() ? (
          <MarkdownMessage content={isUser ? questionContent.body : content} linkedConcepts={isUser ? [] : linkedConcepts} onConceptClick={openConcept} citationIds={validIds} />
        ) : null}

        {!isUser && learningTask?.task_type === 'visual_qa' && learningTask.status === 'waiting_for_input' && onResumeLearningTask && (
          <LearningTaskGate task={learningTask} onResume={onResumeLearningTask} />
        )}
        {!isUser && learningTask?.status === 'waiting_for_confirmation' && (
          <LearningTaskActions initialTask={learningTask} />
        )}
        {!isUser && learningTask?.status === 'interrupted' && onResumeInterruptedTask && (
          <LearningTaskResume task={learningTask} onResume={onResumeInterruptedTask} />
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

        {!isUser && stage === 'done' && subjectSuggestion && (
          <SubjectRouteSuggestionCard suggestion={subjectSuggestion} turnId={turnId} />
        )}

        {showMessageTools && linkedConcepts.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-3 text-xs">
            <span className="text-text-tertiary">相关概念</span>
            {linkedConcepts.slice(0, 8).map((concept) => (
              <button
                key={concept.concept_id || concept.name}
                type="button"
                onClick={() => openConcept(concept)}
                className="border-b border-transparent py-0.5 text-text-secondary hover:border-accent/35 hover:text-accent"
              >
                {concept.name}
              </button>
            ))}
          </div>
        )}

        {showMessageTools && variant === 'document' && (hasStructuredSources || references.length > 0 || sourceChapters.length > 0) && (
          <div className="mt-3 border-t border-border pt-2">
            <button type="button" onClick={openSources} className="flex items-center gap-1 text-xs text-text-secondary transition-colors hover:text-accent">
              <BookOpen className="h-3 w-3" />
              检查来源 {hasStructuredSources ? sources.length : references.length || sourceChapters.length}
            </button>
          </div>
        )}

        {showMessageTools && !isUser && stage === 'done' && messageId && (
          <div className="mt-3 border-t border-border pt-2">
            <div className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
              <span className="mr-1">这次回答有帮助吗？</span>
              <button
                type="button"
                disabled={feedbackBusy}
                aria-label="回答有帮助"
                onClick={() => void submitFeedback('helpful')}
                className={`rounded p-1 transition-colors hover:text-accent ${feedback?.rating === 'helpful' ? 'bg-[var(--accent-softer)] text-accent' : ''}`}
              >
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                disabled={feedbackBusy}
                aria-label="回答没有帮助"
                onClick={() => setShowFeedbackReasons((value) => !value)}
                className={`rounded p-1 transition-colors hover:text-[var(--danger)] ${feedback?.rating === 'unhelpful' ? 'bg-red-50 text-[var(--danger)]' : ''}`}
              >
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
              {feedback && <span>{feedback.rating === 'helpful' ? '已记录' : '已记录问题'}</span>}
            </div>
            {showFeedbackReasons && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {feedbackReasons.map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    disabled={feedbackBusy}
                    onClick={() => void submitFeedback('unhelpful', [value])}
                    className="rounded border border-border px-2 py-1 text-[11px] text-text-secondary transition-colors hover:border-red-300 hover:text-[var(--danger)]"
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            {feedbackError && <div className="mt-1 text-[11px] text-[var(--danger)]">{feedbackError}</div>}
          </div>
        )}
      </article>
    </div>
  );
};

export default ChatMessage;
