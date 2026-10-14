import { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import { post } from '../../../api/client';
import type { ChatMessage } from '../../../contexts/ChatContext';

export type ChatMistakeSource = { status: 'unrecorded' | 'draft' | 'recorded' | 'pending'; message_id?: string; turn_id?: string; draft_id?: string; mistake_id?: string; visibility?: string };
export const ChatMistakeSourcesContext = createContext<{ states: Record<string, ChatMistakeSource>; error: string; loading: boolean; refresh: () => void }>({ states: {}, error: '', loading: true, refresh: () => undefined });

/** One batch per visible message page, refreshed when returning from intake. */
export function useChatMistakeSources(conversationId: string, scope: string, messages: ChatMessage[], active: boolean) {
  const identity = JSON.stringify(messages.filter(m => m.role === 'user' && (m.id || m.turnId)).map(m => ({ id: m.id, turnId: m.turnId })));
  const [snapshot, setSnapshot] = useState<{ key: string; states: Record<string, ChatMistakeSource>; error: string }>({ key: '', states: {}, error: '' });
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const lastStage = messages.at(-1)?.stage;
  const key = `${scope}:${conversationId}:${identity}`;
  const refresh = useCallback(() => setVersion(v => v + 1), []);
  useEffect(() => {
    if (!active) return;
    const refs = JSON.parse(identity) as Array<{ id?: string; turnId?: string }>;
    if (!refs.length) { setSnapshot({ key, states: {}, error: '' }); setLoading(false); return; }
    let alive = true;
    setLoading(true);
    // API contracts are bounded; every loaded question still receives a state.
    void (async () => {
      const states: Record<string, ChatMistakeSource> = {};
      for (let start = 0; start < refs.length; start += 400) {
        const page = refs.slice(start, start + 400);
        const result = await post(`/mistakes/chat-sources/query?book_name=${encodeURIComponent(scope)}`, { conversation_id: conversationId, message_ids: page.filter(r => r.id).map(r => r.id), turn_ids: page.filter(r => !r.id && r.turnId).map(r => r.turnId) });
        if (!result.success) throw new Error(result.message || '错题状态读取失败');
        if (!alive) return;
        for (const state of result.data as ChatMistakeSource[]) states[state.turn_id ? `turn:${state.turn_id}` : state.message_id!] = state;
      }
      if (alive) setSnapshot({ key, states, error: '' });
    })().catch(e => { if (alive) setSnapshot({ key, states: {}, error: e instanceof Error ? e.message : '错题状态暂不可用' }); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [active, conversationId, scope, identity, key, version, messages.length, lastStage]);
  return useMemo(() => ({ states: snapshot.key === key ? snapshot.states : {}, error: snapshot.key === key ? snapshot.error : '', loading: loading || snapshot.key !== key, refresh }), [snapshot, key, loading, refresh]);
}
