import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { get, post } from '../../api/client';
import { readBrowserStorage, writeBrowserStorage } from '../../utils/browserStorage';
import { FocusContext, type FocusSnapshot, type FocusCommand } from './FocusContext';
const pendingKey = 'texa:focus-pending:v1';
export default function FocusProvider({ children }: {
    children: ReactNode;
}) {
    const [data, setData] = useState<FocusSnapshot | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [pending, setPending] = useState(Boolean(readBrowserStorage('sessionStorage', pendingKey))), [remaining, setRemaining] = useState(0);
    const pendingOperation = useRef(readBrowserStorage('sessionStorage', pendingKey));
    const current = useRef<FocusSnapshot | null>(null), gate = useRef(false), epoch = useRef(0), received = useRef(0);
    const accept = useCallback((next: FocusSnapshot) => { if (current.current && next.revision < current.current.revision)
        return; current.current = next; received.current = performance.now(); setData(next); setRemaining(next.remaining_seconds); }, []);
    const refresh = useCallback(async () => { const generation = ++epoch.current; try {
        const response = await get('/focus', 10000);
        if (generation === epoch.current && response.success) {
            accept(response.data);
            setError('');
        }
    }
    catch {
        if (generation === epoch.current)
            setError('专注状态暂不可读取，请恢复连接后重新读取。');
    } }, [accept]);
    useEffect(() => { void refresh(); const resume = () => { if (document.visibilityState === 'visible')
        void refresh(); }; window.addEventListener('online', resume); window.addEventListener('pageshow', resume); document.addEventListener('visibilitychange', resume); return () => { window.removeEventListener('online', resume); window.removeEventListener('pageshow', resume); document.removeEventListener('visibilitychange', resume); }; }, [refresh]);
    useEffect(() => { if (data?.status !== 'running')
        return; const timer = window.setInterval(() => { setRemaining(Math.max(0, data.remaining_seconds - (performance.now() - received.current) / 1000)); }, 1000); return () => window.clearInterval(timer); }, [data]);
    const command = useCallback(async (value: FocusCommand) => { if (gate.current || !current.current || pendingOperation.current)
        return; gate.current = true; epoch.current++; setBusy(true); setError(''); const payload = { ...value, expected_revision: current.current.revision, operation_id: crypto.randomUUID() }; pendingOperation.current = JSON.stringify(payload); writeBrowserStorage('sessionStorage', pendingKey, pendingOperation.current); setPending(true); try {
        const response = await post('/focus/commands', payload, 15000);
        accept(response.data);
        pendingOperation.current = null;
        writeBrowserStorage('sessionStorage', pendingKey, null);
        setPending(false);
    }
    catch (reason) {
        setError(`${reason instanceof Error ? reason.message : '操作结果未确认'}；请核对本次操作。`);
    }
    finally {
        gate.current = false;
        setBusy(false);
    } }, [accept]);
    const reconcile = useCallback(async () => { if (gate.current)
        return; const raw = pendingOperation.current; if (!raw) {
        await refresh();
        return;
    } gate.current = true; setBusy(true); try {
        const payload = JSON.parse(raw);
        const receipt = await get(`/focus/operations/${encodeURIComponent(payload.operation_id)}`, 10000);
        if (receipt.data) {
            accept(receipt.data);
            pendingOperation.current = null;
            writeBrowserStorage('sessionStorage', pendingKey, null);
            setPending(false);
            setError('');
        }
        else {
            await refresh();
            if (current.current?.revision !== payload.expected_revision) {
                pendingOperation.current = null;
                writeBrowserStorage('sessionStorage', pendingKey, null);
                setPending(false);
                setError('本次操作未提交，状态已更新。请按当前状态重新操作。');
                return;
            }
            setError('本次操作尚无提交回执，未确认保存。');
            if (window.confirm('重试同一次专注操作？如果状态已变更，服务器会拒绝覆盖。')) {
                const response = await post('/focus/commands', payload, 15000);
                accept(response.data);
                pendingOperation.current = null;
                writeBrowserStorage('sessionStorage', pendingKey, null);
                setPending(false);
                setError('');
            }
            else {
                pendingOperation.current = null;
                writeBrowserStorage('sessionStorage', pendingKey, null);
                setPending(false);
            }
        }
    }
    catch (reason) {
        setError(reason instanceof Error ? reason.message : '核对失败，请稍后重试');
    }
    finally {
        gate.current = false;
        setBusy(false);
    } }, [accept, refresh]);
    return <FocusContext.Provider value={{ data, busy, error, pending, remaining, refresh, command, reconcile }}>{children}</FocusContext.Provider>;
}
