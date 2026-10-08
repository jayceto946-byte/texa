import '@fontsource/jetbrains-mono/latin-400.css';
import './index.css';
import { lazy, Suspense, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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
  return <Suspense fallback={<div role="status" style={{ padding: 24 }}>正在加载页面…</div>}>{page}</Suspense>;
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
