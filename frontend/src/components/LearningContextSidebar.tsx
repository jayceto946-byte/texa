import { useCallback, useEffect, useMemo, useState } from 'react';
import { MessageSquarePlus, PanelLeftClose } from 'lucide-react';
import { get } from '../api/client';
import type { ChatMessage, ConversationPage } from '../contexts/ChatContext';
import { mapStoredConversationMessages } from '../utils/conversationMessages';
import { buildTextbookScopeOptions, scopeContainsBook, type TextbookRecord } from '../utils/textbookScopes';
import ScopeSelector from './ScopeSelector';

type ConversationSummary = {
  id: string;
  title: string;
  subject: string;
  book_name: string;
  updated_at: string;
  message_count: number;
};

const BOOKS_CACHE_KEY = 'texa:learning-context:books:v1';

function conversationCacheKey(query: string) {
  return `texa:learning-context:conversations:v1:${query}`;
}

function readCache<T>(key: string): T | null {
  try {
    const cached = JSON.parse(window.localStorage.getItem(key) || 'null');
    if (!cached || !Array.isArray(cached.value)) return null;
    return cached.value as T;
  } catch {
    return null;
  }
}

function writeCache<T>(key: string, value: T) {
  try {
    window.localStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), value }));
  } catch {
    // The in-memory state remains authoritative when device storage is unavailable.
  }
}

function relativeTime(value = '') {
  if (!value) return '';
  const time = new Date(value.replace(' ', 'T')).getTime();
  if (!Number.isFinite(time)) return '';
  const diff = Date.now() - time;
  if (diff < 3_600_000) return `${Math.max(1, Math.round(diff / 60_000))} 分钟`;
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)} 小时`;
  return `${Math.round(diff / 86_400_000)} 天`;
}

export default function LearningContextSidebar({
  hidden = false,
  subject,
  bookName,
  conversationId,
  refreshKey,
  onClose,
  onSubjectChange,
  onBookChange,
  onNewConversation,
  onLoadConversation,
}: {
  hidden?: boolean;
  subject: string;
  bookName: string;
  conversationId: string;
  refreshKey: number;
  onClose: () => void;
  onSubjectChange: (value: string) => void;
  onBookChange: (value: string) => void;
  onNewConversation: () => void;
  onLoadConversation: (payload: { id: string; messages: ChatMessage[]; subject: string; bookName: string; page: ConversationPage | null }) => void;
}) {
  const [books, setBooks] = useState<TextbookRecord[]>(() => readCache<TextbookRecord[]>(BOOKS_CACHE_KEY) || []);

  const subjectSuggestions = useMemo(() => Array.from(new Set(books.map((book) => book.subject || '').filter(Boolean))), [books]);
  const scopeBooks = useMemo(() => buildTextbookScopeOptions(books), [books]);
  const selectedScope = useMemo(() => scopeBooks.find((item) => scopeContainsBook(item, bookName)), [bookName, scopeBooks]);

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: '80' });
    const groupedScope = (selectedScope?.sourceNames?.length || 0) > 1;
    if (subject.trim() && !groupedScope) params.set('subject', subject.trim());
    if (bookName.trim() && (selectedScope?.sourceNames?.length || 0) <= 1) params.set('book_name', bookName.trim());
    return params.toString();
  }, [bookName, selectedScope, subject]);
  const groupedNamesKey = (selectedScope?.sourceNames || []).join('\0');
  const initialConversations = readCache<ConversationSummary[]>(conversationCacheKey(query)) || [];
  const [conversations, setConversations] = useState<ConversationSummary[]>(initialConversations);
  const [loading, setLoading] = useState(initialConversations.length === 0);

  const sessionScopeLabel = (item: ConversationSummary) => {
    const sameSubject = (item.subject || '').trim() === (subject || '').trim();
    const sameBookScope = selectedScope
      ? scopeContainsBook(selectedScope, item.book_name || '')
      : (item.book_name || '').trim() === (bookName || '').trim();
    if (sameSubject && sameBookScope) return '';
    return [item.subject || '未分类', item.book_name].filter(Boolean).join(' / ');
  };

  const loadBooks = useCallback(async () => {
    try {
      const res = await get('/books/list', 20000);
      if (res?.success) {
        const nextBooks = res.data || [];
        setBooks(nextBooks);
        writeCache(BOOKS_CACHE_KEY, nextBooks);
      }
    } catch {
      // Keep the last successful snapshot visible while the backend recovers.
    }
  }, []);

  useEffect(() => {
    const onChanged = () => void loadBooks();
    window.addEventListener('books:changed', onChanged);
    void loadBooks();
    return () => window.removeEventListener('books:changed', onChanged);
  }, [loadBooks]);

  useEffect(() => {
    let cancelled = false;
    const cacheKey = conversationCacheKey(query);
    const cachedRows = readCache<ConversationSummary[]>(cacheKey);
    const groupedNames = groupedNamesKey ? groupedNamesKey.split('\0') : [];
    if (cachedRows) {
      setConversations(groupedNames.length > 1
        ? cachedRows.filter((item) => groupedNames.includes(item.book_name))
        : cachedRows);
    } else {
      setLoading(true);
    }
    get(`/chat/conversations?${query}`, 20000)
      .then((res) => {
        if (cancelled) return;
        if (!res?.success) return;
        const rows = res.data || [];
        writeCache(cacheKey, rows);
        setConversations(groupedNames.length > 1
          ? rows.filter((item: ConversationSummary) => groupedNames.includes(item.book_name))
          : rows);
      })
      .catch(() => undefined)
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [conversationId, groupedNamesKey, query, refreshKey]);

  const loadConversation = async (id: string) => {
    const res = await get(`/chat/conversations/${encodeURIComponent(id)}?limit=40`, 20000);
    if (!res?.success || !res.data) return;
    const storedBookName = res.data.book_name || '';
    const logicalScope = scopeBooks.find((item) => scopeContainsBook(item, storedBookName));
    onLoadConversation({
      id: res.data.id,
      messages: mapStoredConversationMessages(res.data.messages || []),
      subject: logicalScope?.subject || res.data.subject || '',
      bookName: storedBookName,
      page: res.data.page || null,
    });
  };

  return (
    <aside className="learning-context-sidebar" aria-label="学习上下文" hidden={hidden}>
      <header className="learning-context-header">
        <h1 className="min-w-0 text-[16px] font-semibold text-text-primary">学习</h1>
        <div className="window-drag-region" aria-hidden="true" />
        <button type="button" onClick={onClose} className="app-icon-button" aria-label="收起学习上下文">
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </header>

      <section className="learning-context-scope" aria-labelledby="learning-scope-title">
        <div id="learning-scope-title" className="context-section-label">当前学习范围</div>
        <ScopeSelector
          subject={subject}
          bookName={bookName}
          books={scopeBooks}
          suggestions={subjectSuggestions}
          onSubjectChange={onSubjectChange}
          onBookChange={onBookChange}
          allowAllSubjects
          fullWidth
          width="wide"
          label="学习范围"
        />
        <button type="button" onClick={onNewConversation} className="context-new-session">
          <MessageSquarePlus className="h-4 w-4" />
          新会话
        </button>
      </section>

      <section className="learning-context-sessions" aria-labelledby="session-list-title">
        <div className="context-session-heading">
          <span id="session-list-title" className="context-section-label">历史记录</span>
          <span className="type-caption text-text-tertiary">{loading && conversations.length === 0 ? '加载中' : conversations.length}</span>
        </div>
        <div className="context-session-list">
          {!loading && conversations.length === 0 && <p className="context-session-empty">当前范围暂无会话</p>}
          {conversations.map((item) => {
            const active = item.id === conversationId;
            const scopeLabel = sessionScopeLabel(item);
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => void loadConversation(item.id)}
                className={`context-session-row ${active ? 'is-active' : ''}`}
                aria-current={active ? 'page' : undefined}
              >
                <span className="context-session-title" title={item.title}>{item.title}</span>
                <span className="context-session-time">{relativeTime(item.updated_at)}</span>
                {scopeLabel && <span className="context-session-scope">{scopeLabel}</span>}
              </button>
            );
          })}
        </div>
      </section>
    </aside>
  );
}
