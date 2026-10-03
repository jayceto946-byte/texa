import { useCallback, useEffect, useRef, useState } from 'react';
import { ConversationError, conversationApi, notifyConversationChange, type BlockingConversationTask, type ConversationAction, type ConversationManagement } from './api';

export function useConversationManagement(id: string, enabled = true) {
  const [entry, setEntry] = useState<{ id: string; management: ConversationManagement } | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(enabled);
  const [busy, setBusy] = useState(false);
  const [tasks, setTasks] = useState<BlockingConversationTask[]>([]);
  const [retry, setRetry] = useState(0);
  const operation = useRef<{ key: string; id: string } | null>(null);
  const management = entry?.id === id ? entry.management : null;

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setLoading(true); setError(''); setTasks([]);
    void conversationApi.management(id, controller.signal).then(value => {
      if (!controller.signal.aborted) setEntry(current => current?.id === id && current.management.revision > value.revision ? current : { id, management: value });
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '无法读取会话状态'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    const changed = (event: Event) => {
      const value = (event as CustomEvent<{ id: string; management: ConversationManagement }>).detail;
      if (value.id === id) { setEntry(current => current?.id === id && current.management.revision > value.management.revision ? current : value); setError(''); }
    };
    window.addEventListener('conversations:changed', changed);
    return () => { controller.abort(); window.removeEventListener('conversations:changed', changed); };
  }, [enabled, id, retry]);

  const change = useCallback(async (action: ConversationAction) => {
    if (!management || busy) return;
    const key = `${id}:${action}:${management.revision}`;
    if (operation.current?.key !== key) operation.current = { key, id: crypto.randomUUID() };
    setBusy(true); setError(''); setTasks([]);
    try {
      const value = await conversationApi.change(id, action, management.revision, operation.current.id);
      setEntry({ id, management: value }); notifyConversationChange(id, value);
      operation.current = null;
    } catch (e) {
      setError(e instanceof Error ? e.message : '会话操作失败');
      if (e instanceof ConversationError) setTasks(e.tasks);
      if (e instanceof ConversationError && e.code === 'revision_conflict') { operation.current = null; setRetry(v => v + 1); }
    } finally { setBusy(false); }
  }, [busy, id, management]);
  return { management, error, loading, busy, tasks, change, reload: () => setRetry(v => v + 1) };
}
