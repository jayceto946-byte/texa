import { useCallback, useEffect, useRef } from 'react';
import { chatAsk, chatStream } from '../api/client';
import { useChatContext } from '../contexts/ChatContext';
import type { AnswerMode, ConceptCandidate } from '../types';
import { mergeChatActivity } from '../utils/chatActivities';

const USE_NON_STREAMING = import.meta.env.VITE_USE_NON_STREAMING === 'true';

export function useChat() {
  const {
    messages,
    isLoading,
    bookName,
    subject,
    conversationId,
    setConversationId,
    syncRecoveredScope,
    setActiveChatAbort,
    cancelActiveChat,
    addMessage,
    updateLastMessage,
    setLoading,
  } = useChatContext();

  const requestSequenceRef = useRef(0);
  const streamContentRef = useRef('');
  const sourceChaptersRef = useRef<string[]>([]);
  const linkedConceptsRef = useRef<ConceptCandidate[]>([]);
  const answerModeRef = useRef<AnswerMode>('auto');
  const scopeReasonRef = useRef('');
  const suggestedAnswerModeRef = useRef<AnswerMode | undefined>(undefined);
  const backendRequestIdRef = useRef('');

  const sendMessage = useCallback(
    (question: string, options: { answerMode?: AnswerMode } = {}) => {
      if (!question.trim() || isLoading) return;

      cancelActiveChat();
      const requestId = ++requestSequenceRef.current;
      const turnId = `turn_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`;
      streamContentRef.current = '';
      sourceChaptersRef.current = [];
      linkedConceptsRef.current = [];
      answerModeRef.current = options.answerMode || 'auto';
      scopeReasonRef.current = '';
      suggestedAnswerModeRef.current = undefined;
      backendRequestIdRef.current = '';

      addMessage({ role: 'user', content: question, turnId });
      setLoading(true);
      addMessage({
        role: 'assistant',
        content: '',
        stage: 'thinking',
        turnId,
        activities: [],
      });

      const fail = (message: string) => {
        if (requestId !== requestSequenceRef.current) return;
        setActiveChatAbort(null);
        updateLastMessage((last) => last.role === 'assistant' ? {
          ...last,
          content: `出错了：${message}`,
          stage: 'error',
          activities: (last.activities || []).map((activity) => activity.status === 'active'
            ? { ...activity, status: 'failed' as const, detail: message }
            : activity),
        } : last);
        setLoading(false);
      };

      if (USE_NON_STREAMING) {
        const ctrl = new AbortController();
        setActiveChatAbort(() => {
          requestSequenceRef.current += 1;
          ctrl.abort();
        });
        (async () => {
          try {
            const result = await chatAsk(question, bookName, subject, conversationId, turnId, ctrl.signal, options.answerMode || 'auto');
            if (requestId !== requestSequenceRef.current) return;
            setActiveChatAbort(null);
            if (result.conversation_id) setConversationId(result.conversation_id);
            if (result.book_name || result.subject) syncRecoveredScope(result.book_name || '', result.subject || '');
            updateLastMessage((last) => {
              if (last.role !== 'assistant') return last;
              return {
                ...last,
                content: result.content,
                stage: 'done',
                linkedConcepts: result.linked_concepts || [],
                sources: (result.sources || []).slice(0, 12),
                sourceChapters: result.chapters || [],
                turnId: result.turn_id || turnId,
                id: result.message_id || last.id,
                requestId: result.request_id || undefined,
                subjectSuggestion: result.subject_suggestion,
                answerMode: result.answer_mode,
                suggestedAnswerMode: result.suggested_answer_mode,
                scopeReason: result.scope_reason,
                originalQuestion: question,
              };
            });
            setLoading(false);
          } catch (err) {
            if (ctrl.signal.aborted) return;
            fail(err instanceof Error ? err.message : String(err));
          }
        })();
        return;
      }

      const abortStream = chatStream(
        question,
        bookName,
        subject,
        conversationId,
        turnId,
        (event) => {
          if (requestId !== requestSequenceRef.current) return;
          if (event.conversation_id) setConversationId(event.conversation_id);
          if (event.stage === 'context') {
            if (event.book_name || event.subject) syncRecoveredScope(event.book_name || '', event.subject || '');
            backendRequestIdRef.current = event.request_id || backendRequestIdRef.current;
            answerModeRef.current = event.answer_mode || answerModeRef.current;
            scopeReasonRef.current = event.scope_reason || '';
            updateLastMessage((last) => last.role === 'assistant' ? {
              ...last,
              activities: mergeChatActivity(last.activities, event.activity),
              answerMode: answerModeRef.current,
              scopeReason: scopeReasonRef.current,
              originalQuestion: question,
            } : last);
            return;
          }
          if (event.stage === 'plan') sourceChaptersRef.current = event.chapters || [];
          if (event.stage === 'done') linkedConceptsRef.current = event.state?.linked_concepts || [];
          if (event.suggested_answer_mode || event.state?.suggested_answer_mode) {
            suggestedAnswerModeRef.current = event.suggested_answer_mode || event.state?.suggested_answer_mode;
          }

          let nextStreamContent = streamContentRef.current;
          if (event.stage === 'generate' && event.replace) {
            nextStreamContent = event.chunk || '';
            streamContentRef.current = nextStreamContent;
          } else if (event.stage === 'generate' && event.chunk) {
            nextStreamContent += event.chunk;
            streamContentRef.current = nextStreamContent;
          }

          updateLastMessage((last) => {
            if (last.role !== 'assistant') return last;
            const next = { ...last };
            const existingActivities = event.stage === 'error'
              ? (last.activities || []).map((activity) => activity.status === 'active'
                ? { ...activity, status: 'failed' as const, detail: event.message || '后端生成失败' }
                : activity)
              : last.activities;
            next.activities = mergeChatActivity(existingActivities, event.activity);
            switch (event.stage) {
              case 'plan':
                if (last.stage !== 'generate' && last.stage !== 'done') {
                  next.stage = 'plan';
                  next.content = event.fast_path ? '快速回答中...' : '分析问题中...';
                }
                break;
              case 'retrieve':
                if (last.stage !== 'generate' && last.stage !== 'done') {
                  next.stage = 'retrieve';
                  next.content = (event.answer_mode || answerModeRef.current) === 'subject_mismatch'
                    ? '确认学科范围...'
                    : event.use_textbook_context === false || event.retrieval_status === 'ordinary_qa'
                      ? '准备回答...'
                    : `检索教材上下文${event.content_count ? ` (${event.content_count})` : ''}...`;
                }
                break;
              case 'chapter':
                if (last.stage !== 'generate' && last.stage !== 'done') {
                  next.stage = 'chapter';
                  next.content = '整理章节内容...';
                }
                break;
              case 'generate':
                next.stage = event.done ? 'done' : 'generate';
                next.content = nextStreamContent || last.content;
                break;
              case 'done': {
                const chapters = sourceChaptersRef.current;
                const linkedConcepts = linkedConceptsRef.current;
                next.stage = 'done';
                next.content = streamContentRef.current || last.content;
                next.sourceChapters = chapters;
                next.sources = (event.state?.evidence_sources || []).slice(0, 12);
                next.linkedConcepts = linkedConcepts;
                next.subjectSuggestion = event.subject_suggestion;
                next.answerMode = event.answer_mode || answerModeRef.current;
                next.suggestedAnswerMode = suggestedAnswerModeRef.current;
                next.scopeReason = event.scope_reason || scopeReasonRef.current;
                next.originalQuestion = question;
                next.id = event.message_id || next.id;
                next.requestId = event.request_id || backendRequestIdRef.current || next.requestId;
                break;
              }
              case 'error':
                next.stage = 'error';
                next.content = `出错了：${event.message || '后端生成失败'}`;
                break;
            }
            return next;
          });

          if (event.stage === 'done' || event.stage === 'error') {
            setActiveChatAbort(null);
            setLoading(false);
          }
        },
        (err) => fail(err.message),
        options.answerMode || 'auto',
      );
      setActiveChatAbort(() => {
        if (requestId === requestSequenceRef.current) requestSequenceRef.current += 1;
        abortStream();
      });
    },
    [bookName, subject, conversationId, isLoading, addMessage, updateLastMessage, setLoading, setConversationId, syncRecoveredScope, setActiveChatAbort, cancelActiveChat]
  );

  const stop = useCallback(() => {
    cancelActiveChat();
    updateLastMessage((last) => {
      if (last.role !== 'assistant' || last.stage === 'done' || last.stage === 'error') return last;
      const activities = (last.activities || []).map((activity) => activity.status === 'active'
        ? { ...activity, status: 'skipped' as const, detail: '用户已停止本次处理' }
        : activity);
      if (last.stage === 'agent') return { ...last, content: '已停止学习工具调用。', stage: 'stopped', activities };
      const content = streamContentRef.current.trim() || (last.content && !last.content.endsWith('...') ? last.content : '已停止生成。');
      return { ...last, content, stage: 'stopped', activities };
    });
    setLoading(false);
  }, [cancelActiveChat, setLoading, updateLastMessage]);

  useEffect(() => () => {
    cancelActiveChat();
    setLoading(false);
  }, [cancelActiveChat, setLoading]);

  return { messages, isLoading, sendMessage, stop };
}
