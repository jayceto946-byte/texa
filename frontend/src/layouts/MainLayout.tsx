import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useOutlet } from 'react-router-dom';
import { AlertTriangle, FileText, Loader2, PanelLeftOpen, RotateCw } from 'lucide-react';
import { get } from '../api/client';
import { useChatContext } from '../contexts/ChatContext';
import type { ChatMessage as ContextChatMessage, ConversationPage } from '../contexts/ChatContext';
import type { DesktopBackendStatus } from '../types/electron';
import AppRail from '../components/AppRail';
import LearningContextSidebar from '../components/LearningContextSidebar';
import ContextInspector from '../components/ui/ContextInspector';
import { useInspector } from '../contexts/InspectorContext';
import SettingsDialog from '../components/settings/SettingsDialog';

function layoutSnapshot() {
  const width = typeof window === 'undefined' ? 1280 : window.innerWidth || 1280;
  return {
    compact: width <= 760,
    contextOverlay: width < 920,
    inspectorReplacesContext: width >= 920 && width < 1440,
  };
}

function PersistentRouteOutlet() {
  const location = useLocation();
  const outlet = useOutlet();
  const routeKey = location.pathname;
  const routeSignature = `${location.pathname}${location.search}${location.hash}`;
  const [cachedOutlets, setCachedOutlets] = useState(() => new Map([
    [routeKey, { signature: routeSignature, outlet }],
  ]));
  let renderedOutlets = cachedOutlets;

  // Keep visited workspaces mounted so their lists, scroll positions, drafts and
  // active streams survive navigation. The active outlet is replaced so router
  // context (including search params) still stays current.
  if (cachedOutlets.get(routeKey)?.signature !== routeSignature) {
    renderedOutlets = new Map(cachedOutlets);
    renderedOutlets.set(routeKey, { signature: routeSignature, outlet });
    setCachedOutlets(renderedOutlets);
  }

  return Array.from(renderedOutlets.entries()).map(([key, cachedRoute]) => {
    const active = key === routeKey;
    return (
      <section
        key={key}
        className="persistent-route-panel"
        hidden={!active}
        aria-hidden={!active || undefined}
      >
        {cachedRoute.outlet}
      </section>
    );
  });
}

const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const initialLayout = layoutSnapshot();
  const [compactLayout, setCompactLayout] = useState(initialLayout.compact);
  const [contextOverlay, setContextOverlay] = useState(initialLayout.contextOverlay);
  const [inspectorReplacesContext, setInspectorReplacesContext] = useState(initialLayout.inspectorReplacesContext);
  const [contextOpen, setContextOpen] = useState(!initialLayout.compact && !initialLayout.contextOverlay);
  const [backendStatus, setBackendStatus] = useState<DesktopBackendStatus | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsMounted, setSettingsMounted] = useState(false);
  const settingsButtonRef = useRef<HTMLButtonElement>(null);
  const restoreContextAfterInspectorRef = useRef(false);
  const { bookName, setBookName, subject, setSubject, conversationId, messages, newConversation, loadConversation } = useChatContext();
  const { inspector, closeInspector } = useInspector();

  const isLearningWorkspace = location.pathname === '/';

  useEffect(() => {
    if (!(location.state as { openSettings?: boolean } | null)?.openSettings) return;
    setSettingsMounted(true);
    setSettingsOpen(true);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, location.state, navigate]);

  const openSettings = useCallback(() => {
    setSettingsMounted(true);
    setSettingsOpen(true);
  }, []);

  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  useEffect(() => {
    const next = layoutSnapshot();
    closeInspector();
    setContextOpen(isLearningWorkspace && !next.compact && !next.contextOverlay);
  }, [closeInspector, isLearningWorkspace, location.pathname]);

  useEffect(() => {
    const updateLayout = () => {
      const next = layoutSnapshot();
      setCompactLayout(next.compact);
      setContextOverlay(next.contextOverlay);
      setInspectorReplacesContext(next.inspectorReplacesContext);
      if (next.compact || next.contextOverlay) setContextOpen(false);
    };
    updateLayout();
    window.addEventListener('resize', updateLayout);
    return () => {
      window.removeEventListener('resize', updateLayout);
    };
  }, []);

  useEffect(() => {
    if (!isLearningWorkspace) return;
    if (inspector && inspectorReplacesContext) {
      if (contextOpen) restoreContextAfterInspectorRef.current = true;
      setContextOpen(false);
      return;
    }
    if (inspector && !inspectorReplacesContext && restoreContextAfterInspectorRef.current && !compactLayout && !contextOverlay) {
      restoreContextAfterInspectorRef.current = false;
      setContextOpen(true);
      return;
    }
    if (!inspector && restoreContextAfterInspectorRef.current && !compactLayout && !contextOverlay) {
      restoreContextAfterInspectorRef.current = false;
      setContextOpen(true);
    }
  }, [compactLayout, contextOpen, contextOverlay, inspector, inspectorReplacesContext, isLearningWorkspace]);

  useEffect(() => {
    const desktop = window.kaoyanDesktop;
    if (!desktop?.getBackendStatus) return;
    let mounted = true;
    desktop.getBackendStatus().then((status) => {
      if (mounted) setBackendStatus(status);
    }).catch(() => undefined);
    const unsubscribe = desktop.onBackendStatus?.((status) => setBackendStatus(status));
    return () => {
      mounted = false;
      unsubscribe?.();
    };
  }, []);

  const retryBackend = async () => {
    setBackendStatus((current) => ({
      status: 'recovering',
      message: '正在重新启动本地服务...',
      maxAttempts: current?.maxAttempts,
    }));
    try {
      const result = await window.kaoyanDesktop?.retryStartup?.();
      if (result && !result.ready) {
        setBackendStatus((current) => ({
          ...current,
          status: 'failed',
          message: result.message || '本地服务恢复失败',
          canRetry: true,
        }));
      }
    } catch (error) {
      setBackendStatus({
        status: 'failed',
        message: error instanceof Error ? error.message : String(error),
        canRetry: true,
      });
    }
  };

  const startNewConversation = () => {
    newConversation();
    if (contextOverlay) setContextOpen(false);
    navigate('/');
  };

  const loadExistingConversation = ({ id, messages: nextMessages, subject: nextSubject, bookName: nextBookName, page }: { id: string; messages: ContextChatMessage[]; subject: string; bookName: string; page: ConversationPage | null }) => {
    loadConversation(id, nextMessages, { subject: nextSubject, bookName: nextBookName, page });
    if (contextOverlay) setContextOpen(false);
    navigate('/');
  };

  const switchBook = async (name: string) => {
    if (!name) {
      setBookName('');
      return;
    }
    try {
      const res = await get(`/books/switch/${encodeURIComponent(name)}`);
      if (res?.success) {
        setBookName(res.data?.name || name);
        if (res.data?.subject) setSubject(res.data.subject);
      } else {
        setBookName(name);
      }
    } catch {
      setBookName(name);
    }
  };

  return (
    <div
      data-layout={compactLayout ? 'compact' : 'desktop'}
      data-context={isLearningWorkspace && contextOpen ? 'open' : 'closed'}
      data-context-overlay={contextOverlay ? 'true' : 'false'}
      data-inspector={inspector ? 'open' : 'closed'}
      className="app-shell"
    >
      <AppRail onOpenSettings={openSettings} settingsButtonRef={settingsButtonRef} />

      <LearningContextSidebar
        hidden={!isLearningWorkspace || !contextOpen}
        subject={subject}
        bookName={bookName}
        conversationId={conversationId}
        refreshKey={messages.length}
        onClose={() => setContextOpen(false)}
        onSubjectChange={setSubject}
        onBookChange={switchBook}
        onNewConversation={startNewConversation}
        onLoadConversation={loadExistingConversation}
      />

      {isLearningWorkspace && contextOpen && contextOverlay && (
        <button type="button" className="context-sidebar-scrim" onClick={() => setContextOpen(false)} aria-label="关闭学习上下文" />
      )}

      <div className="workspace-stage">
        {isLearningWorkspace && !contextOpen && (
          <button type="button" className="context-sidebar-trigger" onClick={() => setContextOpen(true)} aria-label="打开学习上下文" title="学习上下文">
            <PanelLeftOpen className="h-[18px] w-[18px]" />
          </button>
        )}

        <main className="workspace-main">
          {backendStatus && backendStatus.status !== 'ready' && (
            <div className={`relative z-40 flex flex-wrap items-center gap-2 border-b px-3 py-2 text-xs ${backendStatus.status === 'failed' ? 'border-red-200 bg-red-50 text-red-800' : 'border-amber-200 bg-amber-50 text-amber-900'}`} role="status">
              {backendStatus.status === 'failed' ? <AlertTriangle className="h-4 w-4 flex-shrink-0" /> : <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin" />}
              <span className="min-w-0 flex-1">{backendStatus.message}</span>
              {backendStatus.status === 'failed' && (
                <>
                  <button type="button" onClick={() => void retryBackend()} className="inline-flex items-center gap-1 rounded-md border border-current/20 bg-white/70 px-2 py-1 font-medium hover:bg-white">
                    <RotateCw className="h-3.5 w-3.5" /> 重试
                  </button>
                  <button type="button" onClick={() => void window.kaoyanDesktop?.openBackendLog?.()} className="inline-flex items-center gap-1 rounded-md border border-current/20 bg-white/70 px-2 py-1 font-medium hover:bg-white">
                    <FileText className="h-3.5 w-3.5" /> 日志
                  </button>
                </>
              )}
            </div>
          )}
          <div className="app-route-stage">
            <PersistentRouteOutlet />
          </div>
        </main>
        <ContextInspector />
      </div>
      {settingsMounted && <SettingsDialog open={settingsOpen} onClose={closeSettings} />}
    </div>
  );
};

export default MainLayout;
