import { useEffect, useRef } from 'react';
/** Cooperates with the existing Electron close handshake; browser refresh uses beforeunload. */
export function useUnsavedWorkGuard(enabled: boolean, message: string) {
  const allowed = useRef(false);
  useEffect(() => {
    allowed.current = false;
    if (!enabled) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (allowed.current) return;
      event.preventDefault(); event.returnValue = '';
    };
    const unsubscribe = window.kaoyanDesktop?.onPrepareClose?.(async aborted => {
      if (aborted) { allowed.current = false; return true; }
      allowed.current = window.confirm(message);
      return allowed.current;
    });
    window.addEventListener('beforeunload', beforeUnload);
    return () => { window.removeEventListener('beforeunload', beforeUnload); unsubscribe?.(); };
  }, [enabled,message]);
}
