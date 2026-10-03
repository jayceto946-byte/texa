import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MessageSquarePlus, PanelLeftClose, Pin, type LucideIcon } from 'lucide-react';
import { get } from '../api/client';
import { ConversationError, conversationApi, notifyConversationChange, type BlockingConversationTask, type ConversationAction, type ConversationManagement, type ConversationSummary, type ConversationView } from '../features/conversations/api';
import '../features/conversations/conversations.css';
import BlockingTasks from '../features/conversations/BlockingTasks';
import { useNoteCommand } from '../features/notes/NoteCommandContext';
import { useChatContext } from '../contexts/ChatContext';
import OverflowMenu from './ui/OverflowMenu';
import type { ChatMessage, ConversationPage } from '../contexts/ChatContext';
import { mapStoredConversationMessages } from '../utils/conversationMessages';
import { buildTextbookScopeOptions, scopeContainsBook, type TextbookRecord } from '../utils/textbookScopes';

export type LearningCapabilityAction = {
  id: 'tools' | 'goals' | 'plugins';
  label: string;
  icon: LucideIcon;
  onSelect: () => void;
};

const BOOKS_CACHE_KEY = 'texa:learning-context:books:v1';

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
  onNewConversation,
  onLoadConversation,
  capabilityActions = [],
}: {
  hidden?: boolean;
  subject: string;
  bookName: string;
  conversationId: string;
  refreshKey: number | string;
  onClose: () => void;
  onNewConversation: () => void;
  onLoadConversation: (payload: { id: string; messages: ChatMessage[]; subject: string; bookName: string; page: ConversationPage | null }) => void;
  capabilityActions?: readonly LearningCapabilityAction[];
}) {
  const openNote = useNoteCommand();
  const { isLoading } = useChatContext();
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [books, setBooks] = useState<TextbookRecord[]>(() => readCache<TextbookRecord[]>(BOOKS_CACHE_KEY) || []);

  const scopeBooks = useMemo(() => buildTextbookScopeOptions(books), [books]);
  const selectedScope = useMemo(() => scopeBooks.find((item) => scopeContainsBook(item, bookName)), [bookName, scopeBooks]);

  const [view, setView] = useState<ConversationView>('active');
  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: '40', view });
    const names = selectedScope?.sourceNames || [];
    if (names.length > 1) names.forEach(name => params.append('book_names', name));
    else {
      if (subject.trim()) params.set('subject', subject.trim());
      if (bookName.trim()) params.set('book_name', bookName.trim());
    }
    return params.toString();
  }, [bookName, selectedScope, subject, view]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [moreLoading, setMoreLoading] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [blockedConversation, setBlockedConversation] = useState('');
  const [blockingTasks, setBlockingTasks] = useState<BlockingConversationTask[]>([]);
  const [undo, setUndo] = useState<{ id: string; action: ConversationAction; revision: number } | null>(null);
  const requestGeneration = useRef(0);
  const pendingOperation = useRef<{ key: string; id: string } | null>(null);

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
    const changed = () => { setUndo(null); setNotice(''); setRetry(v => v + 1); };
    window.addEventListener('conversations:changed', changed);
    return () => window.removeEventListener('conversations:changed', changed);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    ++requestGeneration.current;
    setConversations([]); setNextCursor(null); setLoading(true); setMoreLoading(false); setError('');
    void conversationApi.list(query, controller.signal).then(page => {
      if (controller.signal.aborted) return;
      setConversations(page.items); setNextCursor(page.next_cursor);
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '读取会话失败'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [conversationId, query, refreshKey, retry]);

  const loadMore = async () => {
    if (!nextCursor || moreLoading) return;
    const generation = requestGeneration.current;
    const params = new URLSearchParams(query); params.set('cursor', nextCursor);
    setMoreLoading(true); setError('');
    try {
      const page = await conversationApi.list(params.toString());
      if (generation !== requestGeneration.current) return;
      setConversations(rows => [...rows, ...page.items.filter(item => !rows.some(row => row.id === item.id))]);
      setNextCursor(page.next_cursor);
    } catch (e) {
      if (generation !== requestGeneration.current) return;
      if (e instanceof ConversationError && e.code === 'invalid_cursor') { setNotice('会话记录已更新，已重新读取最新记录'); setRetry(v => v + 1); }
      else setError(e instanceof Error ? e.message : '读取会话失败');
    }
    finally { if (generation === requestGeneration.current) setMoreLoading(false); }
  };

  const manage = async (id: string, management: ConversationManagement, action: ConversationAction, reversing = false) => {
    if (busy) return;
    const key = `${id}:${action}:${management.revision}`;
    if (pendingOperation.current?.key !== key) pendingOperation.current = { key, id: crypto.randomUUID() };
    setBusy(true); setError(''); setBlockedConversation(''); setBlockingTasks([]);
    try {
      const next = await conversationApi.change(id, action, management.revision, pendingOperation.current.id);
      pendingOperation.current = null;
      notifyConversationChange(id, next);
      const reverse: ConversationAction | null = action === 'pin' ? 'unpin' : action === 'unpin' ? 'pin' : action === 'archive' || action === 'trash' ? 'restore' : management.state === 'archived' ? 'archive' : null;
      setUndo(!reversing && reverse ? { id, action: reverse, revision: next.revision } : null);
      setNotice(reversing ? '已撤销' : ({ pin: '已置顶', unpin: '已取消置顶', archive: '已归档', restore: '已恢复', trash: '已移入回收站，笔记和错题仍保留' })[action]);
    } catch (e) {
      setError(e instanceof Error ? e.message : '会话操作失败');
      if (e instanceof ConversationError && e.code === 'conversation_busy') { setBlockedConversation(id); setBlockingTasks(e.tasks); }
      if (e instanceof ConversationError && e.code === 'revision_conflict') { pendingOperation.current = null; setRetry(v => v + 1); }
    } finally { setBusy(false); }
  };

  const loadConversation = async (id: string) => {
    try {
    const res = await get(`/chat/conversations/${encodeURIComponent(id)}?limit=40`, 20000);
    if (!res?.success || !res.data) throw new Error(res?.message || '无法打开会话');
    const storedBookName = res.data.book_name || '';
    const logicalScope = scopeBooks.find((item) => scopeContainsBook(item, storedBookName));
    onLoadConversation({
      id: res.data.id,
      messages: mapStoredConversationMessages(res.data.messages || []),
      subject: logicalScope?.subject || res.data.subject || '',
      bookName: storedBookName,
      page: res.data.page || null,
    });
    setError('');
    } catch (e) { setError(e instanceof Error ? e.message : '无法打开会话'); }
  };

  return (
    <aside className="learning-context-sidebar" aria-label="学习上下文" hidden={hidden}>
      <header className="learning-context-header">
        <h1 className="min-w-0 text-[16px] font-semibold text-text-primary">学习</h1>
        <div className="window-drag-region" aria-hidden="true" />
        <button type="button" onClick={onNewConversation} className="context-new-session" aria-label="新会话">
          <MessageSquarePlus className="h-4 w-4" />
          <span>新会话</span>
        </button>
        <button type="button" onClick={onClose} className="app-icon-button" aria-label="收起学习上下文">
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </header>

      {capabilityActions.length > 0 && (
        <nav className="learning-capability-navigation" aria-label="学习能力">
          {capabilityActions.map(({ id, label, icon: Icon, onSelect }) => (
            <button key={id} type="button" onClick={onSelect} className="learning-capability-action">
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      )}

      <section className="learning-context-sessions" aria-labelledby="session-list-title">
        <div className="context-session-heading">
          <span id="session-list-title" className="context-section-label">历史记录</span>
          <span className="type-caption text-text-tertiary" title="已加载的会话数">{loading && conversations.length === 0 ? '加载中' : conversations.length}</span>
        </div>
        <nav className="conversation-views" aria-label="会话分类">{(['active', 'archived', 'trashed'] as const).map(value => <button type="button" key={value} aria-pressed={view === value} onClick={() => { setView(value); setError(''); setBlockedConversation(''); }}>{({ active: '最近', archived: '归档', trashed: '回收站' })[value]}</button>)}</nav>
        <div className="context-session-list">
          {error && <div className="context-session-error" role="alert"><p>{error}</p><button className="app-ghost-button" onClick={() => setRetry(v => v + 1)}>重新读取</button>{blockedConversation && <button className="app-ghost-button" onClick={() => void loadConversation(blockedConversation)}>查看未完成任务</button>}</div>}
          {blockingTasks.length > 0 && <BlockingTasks tasks={blockingTasks} onChanged={() => { setBlockingTasks([]); setBlockedConversation(''); setError(''); setNotice('任务已结束，可以重新选择会话操作'); setRetry(v => v + 1); }}/>}
          {notice && <p role="status" className="conversation-notice">{notice}{undo && <button className="app-ghost-button" disabled={busy} onClick={() => void manage(undo.id, { state: view, pinned: false, revision: undo.revision }, undo.action, true)}>撤销</button>}</p>}
          {loading && <p className="context-session-empty" role="status">正在读取会话…</p>}
          {!error && !loading && conversations.length === 0 && <p className="context-session-empty">当前范围暂无会话</p>}
          {conversations.map((item) => {
            const active = item.id === conversationId;
            const scopeLabel = sessionScopeLabel(item);
            return (
              <div className="context-session-entry" key={item.id}><button
                type="button"
                onClick={() => void loadConversation(item.id)}
                className={`context-session-row ${active ? 'is-active' : ''}`}
                aria-current={active ? 'page' : undefined}
              >
                <span className="context-session-title" title={item.title}>{item.management.pinned && <Pin size={12} aria-label="已置顶" className="conversation-pin"/>}{item.title}</span>
                <span className="context-session-time">{relativeTime(item.updated_at)}</span>
                {scopeLabel && <span className="context-session-scope">{scopeLabel}</span>}
              </button><OverflowMenu label={`${item.title}的更多操作`}>{close => <>
                {view !== 'trashed' && <button role="menuitem" disabled={busy} onClick={() => { close(); void manage(item.id, item.management, item.management.pinned ? 'unpin' : 'pin'); }}>{item.management.pinned ? '取消置顶' : '置顶'}</button>}
                {view !== 'trashed' && <button role="menuitem" onClick={() => { close(); openNote({ conversationId: item.id, title: item.title, busy: active && isLoading }); }}>整理为笔记</button>}
                <button role="menuitem" disabled={busy} onClick={() => { close(); void manage(item.id, item.management, view === 'active' ? 'archive' : 'restore'); }}>{view === 'active' ? '归档' : '恢复'}</button>
                {view !== 'trashed' && <button role="menuitem" disabled={busy} onClick={() => { close(); void manage(item.id, item.management, 'trash'); }}>移入回收站</button>}
              </>}</OverflowMenu></div>
            );
          })}
          {nextCursor && <button className="app-ghost-button conversation-load-more" disabled={moreLoading} onClick={() => void loadMore()}>{moreLoading ? '正在读取…' : '加载更多会话'}</button>}
        </div>
      </section>
    </aside>
  );
}
