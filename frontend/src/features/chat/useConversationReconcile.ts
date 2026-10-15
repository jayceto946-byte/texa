import { useEffect, useState } from 'react';
import { get } from '../../api/client';
import { useChatContext } from '../../contexts/ChatContext';
import { mapStoredConversationMessages } from '../../utils/conversationMessages';
export function useConversationReconcile(active: boolean) {
    const { conversationId, isLoading, loadConversation } = useChatContext();
    const [error, setError] = useState('');
    useEffect(() => {
        let cancelled = false;
        let reading = false;
        let lastRead = 0;
        const controller = new AbortController();
        const read = async (event?: Event) => { if (cancelled || reading || !active || isLoading || !conversationId || document.visibilityState !== 'visible' || !navigator.onLine)
            return; if (event?.type !== 'texa:reload-session' && Date.now() - lastRead < 3000)
            return; reading = true; lastRead = Date.now(); try {
            const response = await get(`/chat/conversations/${encodeURIComponent(conversationId)}?limit=40`, 20000, controller.signal);
            if (cancelled)
                return;
            const value = response.data;
            if (!response.success || !value)
                throw new Error('读取会话失败');
            loadConversation(conversationId, mapStoredConversationMessages(value.messages || []), { subject: value.subject, bookName: value.book_name, page: value.page });
            setError('');
        }
        catch {
            if (!cancelled)
                setError('会话状态尚未确认，请恢复连接后重新读取；不要重复提交问题。');
        }
        finally {
            reading = false;
        } };
        const visible = (event: Event) => { if (document.visibilityState === 'visible')
            void read(event); };
        window.addEventListener('online', visible);
        window.addEventListener('pageshow', visible);
        document.addEventListener('visibilitychange', visible);
        window.addEventListener('texa:reload-session', visible);
        return () => { cancelled = true; controller.abort(); window.removeEventListener('online', visible); window.removeEventListener('pageshow', visible); document.removeEventListener('visibilitychange', visible); window.removeEventListener('texa:reload-session', visible); };
    }, [active, conversationId, isLoading, loadConversation]);
    return error;
}
