import { useCallback, useEffect, useMemo, useState } from 'react';
import { BookOpen, History, MessageSquarePlus, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { get } from '../api/client';
import type { ChatMessage } from '../contexts/ChatContext';
import ScopeSelector from './ScopeSelector';
import { buildTextbookScopeOptions, scopeContainsBook, type TextbookRecord } from '../utils/textbookScopes';

type ConversationSummary = {
  id: string;
  title: string;
  subject: string;
  book_name: string;
  updated_at: string;
  message_count: number;
};

const labels = {
  uncategorized: '未分类',
  minutes: '分钟',
  hours: '小时',
  days: '天',
  expandHistory: '展开历史',
  collapseHistory: '收起历史',
  scope: '对话范围',
  newConversation: '新会话',
  history: '历史记录',
  loading: '加载中',
  empty: '暂无对话历史',
};

const subjectColors = ['#0066cc', '#7a7a7a', '#2997ff'];

function colorForSubject(subject = '') {
  const key = subject || labels.uncategorized;
  let hash = 0;
  for (const char of key) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return subjectColors[hash % subjectColors.length];
}

function relativeTime(value = '') {
  if (!value) return '';
  const time = new Date(value.replace(' ', 'T')).getTime();
  if (!Number.isFinite(time)) return '';
  const diff = Date.now() - time;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < hour) return `${Math.max(1, Math.round(diff / minute))} ${labels.minutes}`;
  if (diff < day) return `${Math.round(diff / hour)} ${labels.hours}`;
  return `${Math.round(diff / day)} ${labels.days}`;
}

export default function ChatHistorySidebar({
  open,
  embedded = false,
  subject,
  bookName,
  conversationId,
  refreshKey,
  onToggle,
  onSubjectChange,
  onBookChange,
  onNewConversation,
  onLoadConversation,
}: {
  open: boolean;
  embedded?: boolean;
  subject: string;
  bookName: string;
  conversationId: string;
  refreshKey: number;
  onToggle: () => void;
  onSubjectChange: (value: string) => void;
  onBookChange: (value: string) => void;
  onNewConversation: () => void;
  onLoadConversation: (payload: { id: string; messages: ChatMessage[]; subject: string; bookName: string }) => void;
}) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [books, setBooks] = useState<TextbookRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const shellClass = embedded
    ? 'flex min-h-0 flex-1 flex-col overflow-hidden bg-bg-secondary/60'
    : 'relative flex h-full w-[294px] flex-shrink-0 flex-col border-r border-border bg-bg-secondary/90';
  const headerClass = embedded ? 'border-b border-border px-3 py-3' : 'border-b border-border p-4';

  const subjectSuggestions = useMemo(() => Array.from(new Set(books.map((book) => book.subject || '').filter(Boolean))), [books]);
  const scopeBooks = useMemo(() => buildTextbookScopeOptions(books), [books]);
  const selectedScope = useMemo(() => scopeBooks.find((item) => scopeContainsBook(item, bookName)), [bookName, scopeBooks]);

  const loadBooks = useCallback(async () => {
    try {
      const res = await get('/books/list', 20000);
      setBooks(res?.success ? res.data || [] : []);
    } catch {
      setBooks([]);
    }
  }, []);

  useEffect(() => {
    const onChanged = () => void loadBooks();
    window.addEventListener('books:changed', onChanged);
    void loadBooks();
    return () => window.removeEventListener('books:changed', onChanged);
  }, [loadBooks]);

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: '80' });
    const groupedScope = (selectedScope?.sourceNames?.length || 0) > 1;
    if (subject.trim() && !groupedScope) params.set('subject', subject.trim());
    if (bookName.trim() && (selectedScope?.sourceNames?.length || 0) <= 1) params.set('book_name', bookName.trim());
    return params.toString();
  }, [subject, bookName, selectedScope]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    get(`/chat/conversations?${query}`, 20000)
      .then((res) => {
        if (cancelled) return;
        const rows = res?.success ? res.data || [] : [];
        const groupedNames = selectedScope?.sourceNames || [];
        setConversations(groupedNames.length > 1
          ? rows.filter((item: ConversationSummary) => groupedNames.includes(item.book_name))
          : rows,
        );
      })
      .catch(() => {
        if (!cancelled) setConversations([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, conversationId, refreshKey, selectedScope]);

  const loadConversation = async (id: string) => {
    const res = await get(`/chat/conversations/${encodeURIComponent(id)}`, 20000);
    if (!res?.success || !res.data) return;
    const storedMessages = res.data.messages || [];
    const messages = storedMessages.map((item: any, index: number) => ({
      id: item.id || undefined,
      turnId: item.turn_id || undefined,
      role: item.role === 'assistant' ? 'assistant' : 'user',
      content: item.content || '',
      stage: item.role === 'assistant' ? 'done' : undefined,
      sources: Array.isArray(item.sources) ? item.sources : undefined,
      linkedConcepts: Array.isArray(item.linked_concepts) ? item.linked_concepts : undefined,
      answerMode: item.answer_mode || undefined,
      suggestedAnswerMode: item.suggested_answer_mode || undefined,
      scopeReason: item.scope_reason || undefined,
      originalQuestion: item.role === 'assistant' && storedMessages[index - 1]?.role === 'user' ? storedMessages[index - 1].content : undefined,
    })) as ChatMessage[];
    const storedBookName = res.data.book_name || '';
    const logicalScope = scopeBooks.find((item) => scopeContainsBook(item, storedBookName));
    onLoadConversation({ id: res.data.id, messages, subject: logicalScope?.subject || res.data.subject || '', bookName: storedBookName });
  };

  if (!open) {
    if (embedded) return null;
    return (
      <button type="button" onClick={onToggle} className="absolute left-3 top-4 z-20 flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-bg-card text-text-secondary hover:border-accent hover:text-accent" title={labels.expandHistory}>
        <PanelLeftOpen className="h-4 w-4" />
      </button>
    );
  }

  return (
    <aside className={shellClass}>
      <div className={headerClass}>
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 type-section-title text-text-primary"><BookOpen className="h-4 w-4 text-accent" />{labels.scope}</div>
          {!embedded && <button type="button" onClick={onToggle} className="rounded-lg p-1.5 text-text-secondary hover:bg-bg-card hover:text-text-primary" title={labels.collapseHistory}><PanelLeftClose className="h-4 w-4" /></button>}
        </div>
        <div className="space-y-2">
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
            label={labels.scope}
          />
          <button type="button" onClick={onNewConversation} className="mt-2 flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-border bg-bg-card type-control text-text-primary hover:border-accent/50 hover:bg-[var(--accent-softer)]">
            <MessageSquarePlus className="h-4 w-4" />{labels.newConversation}
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col p-3">
        <div className="mb-2 flex items-center justify-between px-1 type-section-title text-text-primary"><span className="flex items-center gap-2"><History className="h-4 w-4 text-accent" />{labels.history}</span><span className="type-caption font-normal text-text-secondary">{loading ? labels.loading : `${conversations.length}`}</span></div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
          {conversations.length === 0 && <div className="rounded-lg border border-border bg-bg-card/55 px-3 py-5 text-center type-body text-text-secondary">{labels.empty}</div>}
          {conversations.map((item) => {
            const color = colorForSubject(item.subject);
            const active = item.id === conversationId;
            const showColor = !subject.trim();
            return (
              <button key={item.id} type="button" onClick={() => loadConversation(item.id)} className={`relative w-full overflow-hidden rounded-lg border px-3 py-2.5 text-left transition-colors ${active ? 'border-accent/30 bg-bg-card' : 'border-transparent hover:border-border hover:bg-bg-card/80'}`}>
                {showColor && <span className="pointer-events-none absolute inset-y-2 left-0 w-0.5 rounded-full" style={{ backgroundColor: color }} />}
                <div className="relative flex min-w-0 items-center justify-between gap-2 [writing-mode:horizontal-tb]">
                  <div className="min-w-0 flex-1 truncate whitespace-nowrap type-control text-text-primary" title={item.title}>{item.title}</div>
                  <div className="flex-shrink-0 whitespace-nowrap type-caption text-text-secondary">{relativeTime(item.updated_at)}</div>
                </div>
                <div className="relative mt-1 flex min-w-0 items-center gap-1 whitespace-nowrap type-caption text-text-secondary [writing-mode:horizontal-tb]">
                  <span className="min-w-0 truncate">{item.subject || labels.uncategorized}</span>
                  {item.book_name && <><span>/</span><span className="min-w-0 truncate">{item.book_name}</span></>}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
