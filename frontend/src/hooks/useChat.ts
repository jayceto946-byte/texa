import { useCallback, useEffect, useRef } from 'react';
import { AGENT_FALLBACK_TIMEOUT_MS, chatAsk, chatStream, post, runReadOnlyAgent } from '../api/client';
import { useChatContext } from '../contexts/ChatContext';
import type { AnswerMode, ConceptCandidate } from '../types';
import { classifyLearningAgentIntent, learningAgentFallbackStatus, learningAgentStatus } from '../utils/learningAgentRouting';

const USE_NON_STREAMING = import.meta.env.VITE_USE_NON_STREAMING === 'true';

export function useChat() {
  const {
    messages,
    isLoading,
    bookName,
    subject,
    conversationId,
    setConversationId,
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

  const sendMessage = useCallback(
    (question: string, options: { answerMode?: AnswerMode } = {}) => {
      if (!question.trim() || isLoading) return;

      const agentIntent = options.answerMode ? null : classifyLearningAgentIntent(question, Boolean(bookName));
      cancelActiveChat();
      const requestId = ++requestSequenceRef.current;
      const turnId = `turn_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`;
      streamContentRef.current = '';
      sourceChaptersRef.current = [];
      linkedConceptsRef.current = [];
      answerModeRef.current = options.answerMode || 'auto';
      scopeReasonRef.current = '';
      suggestedAnswerModeRef.current = undefined;

      addMessage({ role: 'user', content: question, turnId });
      setLoading(true);
      addMessage({
        role: 'assistant',
        content: agentIntent ? learningAgentStatus(agentIntent) : '',
        stage: agentIntent ? 'agent' : 'thinking',
        turnId,
      });

      const fail = (message: string) => {
        if (requestId !== requestSequenceRef.current) return;
        setActiveChatAbort(null);
        updateLastMessage((last) => last.role === 'assistant' ? { ...last, content: `出错了：${message}`, stage: 'error' } : last);
        setLoading(false);
      };

      if (agentIntent) {
        const ctrl = new AbortController();
        setActiveChatAbort(() => {
          requestSequenceRef.current += 1;
          ctrl.abort();
        });
        (async () => {
          try {
            const result = await runReadOnlyAgent(
              question,
              bookName,
              subject,
              conversationId,
              true,
              ctrl.signal,
            );
            if (requestId !== requestSequenceRef.current) return;
            if (!result.success || result.selected_tools.length === 0) {
              throw new Error('没有找到适合当前任务的学习工具');
            }
            const content = result.answer.trim() || '学习工具已执行，但暂时没有生成文字总结。';
            setActiveChatAbort(null);
            updateLastMessage((last) => last.role === 'assistant' ? {
              ...last,
              content,
              stage: 'done',
              turnId,
              originalQuestion: question,
              agentCard: { question, response: result },
            } : last);
            try {
              const logged = await post('/chat/log', {
                conversation_id: conversationId,
                book_name: bookName,
                subject,
                turn_id: turnId,
                messages: [
                  { role: 'user', content: question, turn_id: turnId },
                  { role: 'assistant', content, turn_id: turnId },
                ],
              }, 15000);
              if (requestId === requestSequenceRef.current && logged?.conversation_id) {
                setConversationId(logged.conversation_id);
              }
            } catch {
              // The in-memory Agent card remains usable if persistence is temporarily unavailable.
            }
            if (requestId === requestSequenceRef.current) setLoading(false);
          } catch (agentError) {
            if (ctrl.signal.aborted || requestId !== requestSequenceRef.current) return;
            updateLastMessage((last) => last.role === 'assistant' ? {
              ...last,
              content: learningAgentFallbackStatus(),
              stage: 'agent',
            } : last);
            try {
              const result = await chatAsk(
                question,
                bookName,
                subject,
                conversationId,
                turnId,
                ctrl.signal,
                options.answerMode || 'auto',
                AGENT_FALLBACK_TIMEOUT_MS,
              );
              if (requestId !== requestSequenceRef.current) return;
              setActiveChatAbort(null);
              if (result.conversation_id) setConversationId(result.conversation_id);
              updateLastMessage((last) => last.role === 'assistant' ? {
                ...last,
                content: result.content,
                stage: 'done',
                linkedConcepts: result.linked_concepts || [],
                sources: (result.sources || []).slice(0, 12),
                sourceChapters: result.chapters || [],
                turnId: result.turn_id || turnId,
                subjectSuggestion: result.subject_suggestion,
                answerMode: result.answer_mode,
                suggestedAnswerMode: result.suggested_answer_mode,
                scopeReason: result.scope_reason,
                originalQuestion: question,
              } : last);
              setLoading(false);
            } catch (fallbackError) {
              if (ctrl.signal.aborted) return;
              const agentMessage = agentError instanceof Error ? agentError.message : String(agentError);
              const fallbackMessage = fallbackError instanceof Error ? fallbackError.message : String(fallbackError);
              fail(`${agentMessage}；普通回答降级也失败：${fallbackMessage}`);
            }
          }
        })();
        return;
      }

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
            answerModeRef.current = event.answer_mode || answerModeRef.current;
            scopeReasonRef.current = event.scope_reason || '';
            updateLastMessage((last) => last.role === 'assistant' ? {
              ...last,
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
    [bookName, subject, conversationId, isLoading, addMessage, updateLastMessage, setLoading, setConversationId, setActiveChatAbort, cancelActiveChat]
  );

  const stop = useCallback(() => {
    cancelActiveChat();
    updateLastMessage((last) => {
      if (last.role !== 'assistant' || last.stage === 'done' || last.stage === 'error') return last;
      if (last.stage === 'agent') return { ...last, content: '已停止学习工具调用。', stage: 'stopped' };
      const content = streamContentRef.current.trim() || (last.content && !last.content.endsWith('...') ? last.content : '已停止生成。');
      return { ...last, content, stage: 'stopped' };
    });
    setLoading(false);
  }, [cancelActiveChat, setLoading, updateLastMessage]);

  useEffect(() => () => {
    cancelActiveChat();
    setLoading(false);
  }, [cancelActiveChat, setLoading]);

  return { messages, isLoading, sendMessage, stop };
}
