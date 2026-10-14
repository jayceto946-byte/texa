import { useLayoutEffect, useRef, useState } from 'react';
import type { ChatMessage } from '../../contexts/ChatContext';

export function isNearReadingBottom(element: Pick<HTMLElement, 'scrollHeight' | 'scrollTop' | 'clientHeight'>) {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= 64;
}

/** One reading policy for deltas, session changes and explicit source/history anchors. */
export function useReadingScroll(messages: ChatMessage[], conversationId: string, active: boolean) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const targetMessageRef = useRef<string | null>(null);
  const preserveHistoryScrollRef = useRef<{ height: number; top: number } | null>(null);
  const follow = useRef(true);
  const [following, setFollowing] = useState(true);
  const previous = useRef<{ conversationId: string; user: unknown }>({ conversationId: '', user: null });
  const onScroll = () => {
    if (!scrollRef.current) return;
    follow.current = isNearReadingBottom(scrollRef.current);
    setFollowing(follow.current);
  };
  const scrollToLatest = () => {
    follow.current = true;
    setFollowing(true);
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  };
  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!container || !active) return;
    const latestUser = [...messages].reverse().find(message => message.role === 'user');
    const user = latestUser?.turnId || latestUser?.id || latestUser;
    if (previous.current.conversationId !== conversationId || previous.current.user !== user) follow.current = true;
    previous.current = { conversationId, user };
    if (targetMessageRef.current) {
      const target = Array.from(container.querySelectorAll<HTMLElement>('[data-message-id]')).find(el => el.dataset.messageId === targetMessageRef.current);
      if (target) {
        target.scrollIntoView({ block: 'center' });
        target.focus({ preventScroll: true });
        targetMessageRef.current = null;
        follow.current = isNearReadingBottom(container);
        setFollowing(follow.current);
        return;
      }
    }
    const preserved = preserveHistoryScrollRef.current;
    if (preserved) {
      preserveHistoryScrollRef.current = null;
      container.scrollTop = preserved.top + container.scrollHeight - preserved.height;
      follow.current = isNearReadingBottom(container);
    } else if (follow.current) {
      container.scrollTop = container.scrollHeight;
    }
    setFollowing(follow.current);
  }, [messages, conversationId, active]);
  return { scrollRef, targetMessageRef, preserveHistoryScrollRef, following, onScroll, scrollToLatest };
}
