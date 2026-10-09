import '@fontsource/jetbrains-mono/latin-400.css';
import './index.css';
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ChatProvider } from './contexts/ChatContext';
import MainLayout from './layouts/MainLayout';
import DesktopTitleBar from './components/DesktopTitleBar';
import { isRemoteBrowser } from './api/client';
const FirstRunGuide = lazy(() => import('./components/FirstRunGuide'));
import { InspectorProvider } from './contexts/InspectorContext';

const GoalsPage = lazy(() => import('./pages/GoalsPage'));
const NotesPage = lazy(() => import('./pages/NotesPage'));
const NoteDetailPage = lazy(() => import('./pages/NoteDetailPage'));
const NoteDraftPage = lazy(() => import('./pages/NoteDraftPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const MistakesPage = lazy(() => import('./pages/MistakesPage'));
const MistakeDetailPage = lazy(() => import('./pages/MistakesPage').then(m => ({ default: m.MistakeDetailPage })));
const MistakeDiagnosisPage = lazy(() => import('./pages/MistakesPage').then(m => ({ default: m.MistakeDiagnosisPage })));
const MistakeIntakePage = lazy(() => import('./pages/MistakeIntakePage'));
const ExercisesPage = lazy(() => import('./pages/ExercisesPage'));
const BooksPage = lazy(() => import('./pages/BooksPage'));
const HighlightPage = lazy(() => import('./pages/HighlightPage'));
const LearningPage = lazy(() => import('./pages/LearningPage'));
const ReviewSessionPage = lazy(() => import('./pages/ReviewSessionPage'));
const WeeklyReportPage = lazy(() => import('./pages/WeeklyReportPage'));
const SettingsPage = lazy(() => import('./components/SystemHealth'));

function loadingPage(page: ReactNode) {
  return <PageSlot>{page}</PageSlot>;
}

function PageLoading() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 20000);
    return () => window.clearTimeout(timer);
  }, []);
  return <div role="status" style={{ padding: 24 }}>
    <p>{slow ? '页面文件下载较慢，请检查手机与桌面的连接。' : '正在加载页面…'}</p>
    {slow && <button type="button" className="app-secondary-button" onClick={() => window.location.reload()}>刷新并重新读取页面</button>}
  </div>;
}

function PageSlot({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <ErrorBoundary resetKey={location.pathname} fallback={<div role="alert" style={{ padding: 24 }}>
    <p>页面文件未能加载，桌面更新后请刷新以读取当前版本。</p>
    <button type="button" className="app-secondary-button" onClick={() => window.location.reload()}>刷新页面</button>
  </div>}><Suspense fallback={<PageLoading />}>{children}</Suspense></ErrorBoundary>;
}

function FirstRunGate({ children }: { children: ReactNode }) {
  // The authenticated remote gate has already verified desktop configuration.
  if (isRemoteBrowser()) return children;
  return <Suspense fallback={<div role="status" style={{ padding: 24 }}>正在读取本地配置…</div>}>
    <FirstRunGuide>{children}</FirstRunGuide>
  </Suspense>;
}

function Workspace() {
  return (
    <ChatProvider>
      <InspectorProvider>
        <DesktopTitleBar />
        <BrowserRouter>
          <FirstRunGate>
          <Routes>
            <Route path="/" element={<MainLayout />}>
              <Route index element={loadingPage(<ChatPage />)} />
              <Route path="goals" element={loadingPage(<GoalsPage />)} />
              <Route path="notes" element={loadingPage(<NotesPage />)} />
              <Route path="notes/drafts/:draftId" element={loadingPage(<NoteDraftPage />)} />
              <Route path="notes/:noteId" element={loadingPage(<NoteDetailPage />)} />
              <Route path="mistakes" element={loadingPage(<MistakesPage />)} />
              <Route path="mistakes/diagnosis" element={loadingPage(<MistakeDiagnosisPage />)} />
              <Route path="mistakes/intake" element={loadingPage(<MistakeIntakePage />)} />
              <Route path="mistakes/intake/:draftId" element={loadingPage(<MistakeIntakePage />)} />
              <Route path="mistakes/review" element={<Navigate to="/learning/review" replace />} />
              <Route path="mistakes/:id" element={loadingPage(<MistakeDetailPage />)} />
              <Route path="exercises" element={loadingPage(<ExercisesPage />)} />
              <Route path="kg" element={<Navigate to="/learning" replace />} />
              <Route path="learning" element={loadingPage(<LearningPage />)} />
              <Route path="learning/review" element={loadingPage(<ReviewSessionPage />)} />
              <Route path="learning/review/:sessionId" element={loadingPage(<ReviewSessionPage />)} />
              <Route path="weekly" element={loadingPage(<WeeklyReportPage />)} />
              <Route path="books" element={loadingPage(<SettingsPage standaloneTab="subjects" />)} />
              <Route path="books/import" element={loadingPage(<BooksPage />)} />
              <Route path="highlights" element={loadingPage(<HighlightPage />)} />
              <Route path="settings" element={<Navigate to="/" replace state={{ openSettings: true }} />} />
            </Route>
          </Routes>
          </FirstRunGate>
        </BrowserRouter>
      </InspectorProvider>
    </ChatProvider>
  );
}

export default Workspace;
