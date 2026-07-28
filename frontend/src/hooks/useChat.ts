import { useCallback, useEffect, useRef } from 'react';
import { chatAsk, chatStream } from '../api/client';
import { useChatContext } from '../contexts/ChatContext';
import type { ConceptCandidate } from '../types';

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

  const sendMessage = useCallback(
    (question: string) => {
      if (!question.trim() || isLoading) return;

      cancelActiveChat();
      const requestId = ++requestSequenceRef.current;
      const turnId = `turn_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`;
      streamContentRef.current = '';
      sourceChaptersRef.current = [];
      linkedConceptsRef.current = [];

      addMessage({ role: 'user', content: question, turnId });
      setLoading(true);
      addMessage({ role: 'assistant', content: '', stage: 'thinking', turnId });

      const fail = (message: string) => {
        if (requestId !== requestSequenceRef.current) return;
        setActiveChatAbort(null);
        updateLastMessage((last) => last.role === 'assistant' ? { ...last, content: `出错了：${message}`, stage: 'error' } : last);
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
            const result = await chatAsk(question, bookName, subject, conversationId, turnId, ctrl.signal);
            if (requestId !== requestSequenceRef.current) return;
            setActiveChatAbort(null);
            if (result.conversation_id) setConversationId(result.conversation_id);
            updateLastMessage((last) => {
              if (last.role !== 'assistant') return last;
              const chapters = result.chapters || [];
              const suffix = chapters.length > 0 && chapters[0] ? `\n\n*来源：${chapters.length > 1 ? `${chapters[0]} 等 ${chapters.length} 个章节` : chapters[0]}*` : '';
              return { ...last, content: `${result.content}${suffix}`, stage: 'done', linkedConcepts: result.linked_concepts || [], turnId: result.turn_id || turnId, subjectSuggestion: result.subject_suggestion };
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
          if (event.stage === 'context') return;
          if (event.stage === 'plan') sourceChaptersRef.current = event.chapters || [];
          if (event.stage === 'done') linkedConceptsRef.current = event.state?.linked_concepts || [];

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
                  next.content = `检索教材上下文${event.content_count ? ` (${event.content_count})` : ''}...`;
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
                const base = streamContentRef.current || last.content;
                const suffix = chapters.length > 0 && chapters[0] ? `\n\n*来源：${chapters.length > 1 ? `${chapters[0]} 等 ${chapters.length} 个章节` : chapters[0]}*` : '';
                next.stage = 'done';
                next.content = `${base}${suffix}`;
                next.sourceChapters = chapters;
                next.linkedConcepts = linkedConcepts;
                next.subjectSuggestion = event.subject_suggestion;
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
        (err) => fail(err.message)
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
