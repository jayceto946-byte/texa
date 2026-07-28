import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import type { ChatAgentCard, ChatChapterHighlightCard, ChatExerciseCard, ChatReportCard, ChatUtilityCard, ConceptCandidate, SubjectRouteSuggestion } from '../types';

export interface ChatMessage {
  role: 'user' | 'assistant';
  id?: string;
  turnId?: string;
  content: string;
  stage?: string;
  sourceChapters?: string[];
  linkedConcepts?: ConceptCandidate[];
  reportCard?: ChatReportCard;
  exerciseCard?: ChatExerciseCard;
  chapterHighlightCard?: ChatChapterHighlightCard;
  utilityCard?: ChatUtilityCard;
  agentCard?: ChatAgentCard;
  subjectSuggestion?: SubjectRouteSuggestion;
}

interface ChatContextType {
  messages: ChatMessage[];
  isLoading: boolean;
  bookName: string;
  subject: string;
  conversationId: string;
  setBookName: (name: string) => void;
  setSubject: (subject: string) => void;
  setConversationId: (id: string) => void;
  setActiveChatAbort: (abort: (() => void) | null) => void;
  cancelActiveChat: () => void;
  loadConversation: (id: string, messages: ChatMessage[], meta?: { subject?: string; bookName?: string }) => void;
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
  const activeChatAbortRef = useRef<(() => void) | null>(null);

  const setActiveChatAbort = useCallback((abort: (() => void) | null) => {
    activeChatAbortRef.current = abort;
  }, []);

  const cancelActiveChat = useCallback(() => {
    const abort = activeChatAbortRef.current;
    activeChatAbortRef.current = null;
    abort?.();
  }, []);

  const persistSubject = useCallback((next: string) => {
    setSubject(next);
    window.localStorage.setItem('kaoyan_subject', next);
  }, []);

  const persistConversationId = useCallback((next: string) => {
    setConversationId(next);
    window.localStorage.setItem('kaoyan_conversation_id', next);
  }, []);

  const newConversation = useCallback(() => {
    cancelActiveChat();
    const next = createConversationId();
    persistConversationId(next);
    setIsLoading(false);
    setMessages([]);
  }, [cancelActiveChat, persistConversationId]);

  const loadConversation = useCallback((id: string, nextMessages: ChatMessage[], meta: { subject?: string; bookName?: string } = {}) => {
    cancelActiveChat();
    persistConversationId(id);
    setIsLoading(false);
    setMessages(nextMessages);
    if (meta.subject !== undefined) persistSubject(meta.subject);
    if (meta.bookName !== undefined) setBookName(meta.bookName);
  }, [cancelActiveChat, persistConversationId, persistSubject]);

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
  }, [cancelActiveChat]);

  const value = useMemo(
    () => ({
      messages,
      isLoading,
      bookName,
      subject,
      conversationId,
      setBookName,
      setSubject: persistSubject,
      setConversationId: persistConversationId,
      setActiveChatAbort,
      cancelActiveChat,
      loadConversation,
      newConversation,
      addMessage,
      updateLastMessage,
      setLoading: setIsLoading,
      clearMessages,
    }),
    [messages, isLoading, bookName, subject, conversationId, persistSubject, persistConversationId, setActiveChatAbort, cancelActiveChat, loadConversation, newConversation, addMessage, updateLastMessage, clearMessages]
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
};

export function useChatContext(): ChatContextType {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used within ChatProvider');
  return ctx;
}
