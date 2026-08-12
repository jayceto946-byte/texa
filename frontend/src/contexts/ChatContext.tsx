import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import type { AnswerMode, AssistantSource, ChatAgentCard, ChatChapterHighlightCard, ChatExerciseCard, ChatReportCard, ChatUtilityCard, ConceptCandidate, SubjectRouteSuggestion } from '../types';

export interface ChatMessage {
  role: 'user' | 'assistant';
  id?: string;
  turnId?: string;
  requestId?: string;
  content: string;
  stage?: string;
  sourceChapters?: string[];
  sources?: AssistantSource[];
  linkedConcepts?: ConceptCandidate[];
  reportCard?: ChatReportCard;
  exerciseCard?: ChatExerciseCard;
  chapterHighlightCard?: ChatChapterHighlightCard;
  utilityCard?: ChatUtilityCard;
  agentCard?: ChatAgentCard;
  subjectSuggestion?: SubjectRouteSuggestion;
  answerMode?: AnswerMode;
  suggestedAnswerMode?: AnswerMode;
  scopeReason?: string;
  originalQuestion?: string;
  answerFeedback?: { rating: 'helpful' | 'unhelpful'; reasons?: string[]; updated_at?: string };
}

export interface ConversationPage {
  has_more: boolean;
  next_before_seq?: number | null;
  limit: number;
  total: number;
}

interface ChatContextType {
  messages: ChatMessage[];
  isLoading: boolean;
  bookName: string;
  subject: string;
  conversationId: string;
  historyPage: ConversationPage | null;
  setBookName: (name: string) => void;
  setSubject: (subject: string) => void;
  setConversationId: (id: string) => void;
  syncRecoveredScope: (bookName: string, subject: string) => void;
  setActiveChatAbort: (abort: (() => void) | null) => void;
  cancelActiveChat: () => void;
  loadConversation: (id: string, messages: ChatMessage[], meta?: { subject?: string; bookName?: string; page?: ConversationPage | null }) => void;
  prependConversationMessages: (messages: ChatMessage[], page: ConversationPage) => void;
  newConversation: () => void;
  addMessage: (msg: ChatMessage) => void;
  updateLastMessage: (updater: (msg: ChatMessage) => ChatMessage) => void;
  setLoading: (loading: boolean) => void;
  clearMessages: () => void;
}

const ChatContext = createContext<ChatContextType | null>(null);

function createConversationId() {
  return `conv_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`;
}

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [bookName, setBookName] = useState('');
  const [subject, setSubject] = useState(() => window.localStorage.getItem('kaoyan_subject') || '数学');
  const [conversationId, setConversationId] = useState(() => window.localStorage.getItem('kaoyan_conversation_id') || createConversationId());
  const [historyPage, setHistoryPage] = useState<ConversationPage | null>(null);
  const activeChatAbortRef = useRef<(() => void) | null>(null);

  const setActiveChatAbort = useCallback((abort: (() => void) | null) => {
    activeChatAbortRef.current = abort;
  }, []);

  const cancelActiveChat = useCallback(() => {
    const abort = activeChatAbortRef.current;
    activeChatAbortRef.current = null;
    abort?.();
  }, []);

  const persistConversationId = useCallback((next: string) => {
    setConversationId(next);
    window.localStorage.setItem('kaoyan_conversation_id', next);
  }, []);

  const resetConversationForScopeChange = useCallback(() => {
    cancelActiveChat();
    persistConversationId(createConversationId());
    setIsLoading(false);
    setMessages([]);
    setHistoryPage(null);
  }, [cancelActiveChat, persistConversationId]);

  const persistSubject = useCallback((next: string) => {
    if (next === subject) return;
    setSubject(next);
    window.localStorage.setItem('kaoyan_subject', next);
    resetConversationForScopeChange();
  }, [resetConversationForScopeChange, subject]);

  const persistBookName = useCallback((next: string) => {
    if (next === bookName) return;
    setBookName(next);
    resetConversationForScopeChange();
  }, [bookName, resetConversationForScopeChange]);

  const newConversation = useCallback(() => {
    cancelActiveChat();
    const next = createConversationId();
    persistConversationId(next);
    setIsLoading(false);
    setMessages([]);
    setHistoryPage(null);
  }, [cancelActiveChat, persistConversationId]);

  const syncRecoveredScope = useCallback((nextBookName: string, nextSubject: string) => {
    if (nextBookName) setBookName(nextBookName);
    if (nextSubject) {
      setSubject(nextSubject);
      window.localStorage.setItem('kaoyan_subject', nextSubject);
    }
  }, []);

  const loadConversation = useCallback((id: string, nextMessages: ChatMessage[], meta: { subject?: string; bookName?: string; page?: ConversationPage | null } = {}) => {
    cancelActiveChat();
    persistConversationId(id);
    setIsLoading(false);
    setMessages(nextMessages);
    setHistoryPage(meta.page || null);
    if (meta.subject !== undefined) {
      setSubject(meta.subject);
      window.localStorage.setItem('kaoyan_subject', meta.subject);
    }
    if (meta.bookName !== undefined) setBookName(meta.bookName);
  }, [cancelActiveChat, persistConversationId]);

  const prependConversationMessages = useCallback((olderMessages: ChatMessage[], page: ConversationPage) => {
    setMessages((current) => {
      const existingIds = new Set(current.map((item) => item.id).filter(Boolean));
      const uniqueOlder = olderMessages.filter((item) => !item.id || !existingIds.has(item.id));
      return [...uniqueOlder, ...current];
    });
    setHistoryPage(page);
  }, []);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const updateLastMessage = useCallback((updater: (msg: ChatMessage) => ChatMessage) => {
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const newMsgs = [...prev];
      newMsgs[newMsgs.length - 1] = updater(newMsgs[newMsgs.length - 1]);
      return newMsgs;
    });
  }, []);

  const clearMessages = useCallback(() => {
    cancelActiveChat();
    setIsLoading(false);
    setMessages([]);
    setHistoryPage(null);
  }, [cancelActiveChat]);

  const value = useMemo(
    () => ({
      messages,
      isLoading,
      bookName,
      subject,
      conversationId,
      historyPage,
      setBookName: persistBookName,
      setSubject: persistSubject,
      setConversationId: persistConversationId,
      syncRecoveredScope,
      setActiveChatAbort,
      cancelActiveChat,
      loadConversation,
      prependConversationMessages,
      newConversation,
      addMessage,
      updateLastMessage,
      setLoading: setIsLoading,
      clearMessages,
    }),
    [messages, isLoading, bookName, subject, conversationId, historyPage, persistBookName, persistSubject, persistConversationId, syncRecoveredScope, setActiveChatAbort, cancelActiveChat, loadConversation, prependConversationMessages, newConversation, addMessage, updateLastMessage, clearMessages]
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
};

export function useChatContext(): ChatContextType {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used within ChatProvider');
  return ctx;
}
