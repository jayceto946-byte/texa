import { ArrowRight, FolderInput, Tags, X } from 'lucide-react';
import { useState } from 'react';

import { patch as patchApi, post } from '../../api/client';
import { useChatContext, type ChatMessage } from '../../contexts/ChatContext';
import type { SubjectRouteSuggestion } from '../../types';

const labels = {
  title: '\u6216\u8bb8\u4f60\u5728\u95ee',
  moveTurn: '\u79fb\u52a8\u672c\u8f6e',
  moveConversation: '\u5f52\u7c7b\u6574\u4e2a\u4f1a\u8bdd',
  dismiss: '\u5ffd\u7565',
  moving: '\u5904\u7406\u4e2d...',
  failed: '\u64cd\u4f5c\u5931\u8d25',
  confidence: '\u5224\u65ad\u7f6e\u4fe1\u5ea6',
};

function mapMessages(items: any[]): ChatMessage[] {
  return (items || []).map((item) => ({
    id: item.id || undefined,
    turnId: item.turn_id || undefined,
    role: item.role === 'assistant' ? 'assistant' : 'user',
    content: item.content || '',
    stage: item.role === 'assistant' ? 'done' : undefined,
  }));
}

export default function SubjectRouteSuggestionCard({
  suggestion,
  turnId,
}: {
  suggestion: SubjectRouteSuggestion;
  turnId?: string;
}) {
  const {
    conversationId,
    setBookName,
    setSubject,
    loadConversation,
  } = useChatContext();
  const [busy, setBusy] = useState<'turn' | 'conversation' | 'dismiss' | null>(null);
  const [resolved, setResolved] = useState(false);
  const [error, setError] = useState('');

  const payload = {
    subject: suggestion.target_subject,
    book_name: suggestion.target_book_name || '',
    source_subject: suggestion.current_subject || '',
  };

  const moveTurn = async () => {
    if (!turnId || busy) return;
    setBusy('turn');
    setError('');
    try {
      const res = await post(`/chat/conversations/${encodeURIComponent(conversationId)}/split-turn`, {
        ...payload,
        turn_id: turnId,
      });
      if (!res?.success || !res.data?.target) throw new Error(res?.message || labels.failed);
      const target = res.data.target;
      loadConversation(target.id, mapMessages(target.messages), {
        subject: target.subject || suggestion.target_subject,
        bookName: target.book_name || '',
      });
      setResolved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : labels.failed);
    } finally {
      setBusy(null);
    }
  };

  const moveConversation = async () => {
    if (busy) return;
    setBusy('conversation');
    setError('');
    try {
      const res = await patchApi(`/chat/conversations/${encodeURIComponent(conversationId)}/scope`, payload);
      if (!res?.success) throw new Error(res?.message || labels.failed);
      setSubject(suggestion.target_subject);
      setBookName(suggestion.target_book_name || '');
      setResolved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : labels.failed);
    } finally {
      setBusy(null);
    }
  };

  const dismiss = async () => {
    if (busy) return;
    setBusy('dismiss');
    try {
      await post('/chat/subject-routing/feedback', {
        source_subject: suggestion.current_subject || '',
        target_subject: suggestion.target_subject,
        action: 'dismissed',
      });
    } catch {
      // Dismissal is local-first; feedback persistence must not trap the card onscreen.
    } finally {
      setResolved(true);
      setBusy(null);
    }
  };

  if (resolved) return null;

  return (
    <div className="mt-4 rounded-xl border border-accent/25 bg-[var(--accent-softer)] p-3 text-text-primary">
      <div className="flex items-start gap-2">
        <Tags className="mt-0.5 h-4 w-4 flex-shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
            <span>{labels.title}</span>
            <ArrowRight className="h-3.5 w-3.5 text-text-secondary" />
            <span className="text-accent">{suggestion.target_subject}</span>
          </div>
          {suggestion.reason && <p className="mt-1 text-xs leading-5 text-text-secondary">{suggestion.reason}</p>}
          <p className="mt-1 text-[11px] text-text-secondary">{labels.confidence} {Math.round(suggestion.confidence * 100)}%</p>
          {error && <p className="mt-2 text-xs text-[var(--danger)]">{error}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={moveTurn} disabled={!turnId || Boolean(busy)} className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs text-white disabled:opacity-50">
              <FolderInput className="h-3.5 w-3.5" />{busy === 'turn' ? labels.moving : labels.moveTurn}
            </button>
            <button type="button" onClick={moveConversation} disabled={Boolean(busy)} className="rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs hover:border-accent/50 disabled:opacity-50">
              {busy === 'conversation' ? labels.moving : labels.moveConversation}
            </button>
            <button type="button" onClick={dismiss} disabled={Boolean(busy)} className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-text-secondary hover:text-text-primary disabled:opacity-50">
              <X className="h-3.5 w-3.5" />{labels.dismiss}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
