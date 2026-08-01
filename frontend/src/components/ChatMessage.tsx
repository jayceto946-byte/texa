import React, { useMemo, useState } from 'react';
import { Bot, BookOpen, User } from 'lucide-react';
import type { ChatAgentCard, ChatChapterHighlightCard, ChatExerciseCard, ChatReportCard, ChatUtilityCard, ConceptCandidate, SubjectRouteSuggestion } from '../types';
import { useChatContext } from '../contexts/ChatContext';
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
  turnId?: string;
  subjectSuggestion?: SubjectRouteSuggestion;
  reportCard?: ChatReportCard;
  exerciseCard?: ChatExerciseCard;
  chapterHighlightCard?: ChatChapterHighlightCard;
  utilityCard?: ChatUtilityCard;
  agentCard?: ChatAgentCard;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, variant = 'message', stage, turnId, subjectSuggestion, linkedConcepts = [], reportCard, exerciseCard, chapterHighlightCard, utilityCard, agentCard }) => {
  const [showSources, setShowSources] = useState(false);
  const [activeConcept, setActiveConcept] = useState<ConceptCandidate | null>(null);
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

  const isUser = role === 'user';
  const isThinking = !isUser && (stage === 'thinking' || stage === 'plan') && !content.trim();
  const hasCard = Boolean(reportCard || exerciseCard || chapterHighlightCard || utilityCard || agentCard);
  const showMessageTools = !hasCard && !isThinking;

  return (
    <div className={variant === 'document' ? 'min-w-0' : `mb-5 flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={variant === 'document' ? 'min-w-0 text-text-primary' : `max-w-[min(96%,820px)] rounded-2xl px-3 py-3 sm:max-w-[min(86%,820px)] sm:px-4 ${isUser ? 'bg-accent text-white' : 'border border-border bg-bg-card text-text-primary'}`}>
        {variant === 'message' && <div className="mb-2 flex items-center gap-2">
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4 text-accent" />}
          <span className="text-xs opacity-70">{isUser ? '你' : 'AI 助手'}</span>
        </div>}

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
          <MarkdownMessage content={content} linkedConcepts={isUser ? [] : linkedConcepts} onConceptClick={setActiveConcept} />
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

        {showMessageTools && references.length > 0 && (
          <div className="mt-3 border-t border-border pt-2">
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