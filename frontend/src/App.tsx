import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ChatProvider } from './contexts/ChatContext';
import MainLayout from './layouts/MainLayout';
import DesktopTitleBar from './components/DesktopTitleBar';
import FirstRunGuide from './components/FirstRunGuide';
import { InspectorProvider } from './contexts/InspectorContext';

const ChatPage = lazy(() => import('./pages/ChatPage'));
const MistakesPage = lazy(() => import('./pages/MistakesPage'));
const ExercisesPage = lazy(() => import('./pages/ExercisesPage'));
const BooksPage = lazy(() => import('./pages/BooksPage'));
const HighlightPage = lazy(() => import('./pages/HighlightPage'));
const LearningPage = lazy(() => import('./pages/LearningPage'));
const WeeklyReportPage = lazy(() => import('./pages/WeeklyReportPage'));
const SettingsPage = lazy(() => import('./components/SystemHealth'));

function App() {
  return (
    <ChatProvider>
      <InspectorProvider>
        <DesktopTitleBar />
        <FirstRunGuide />
        <BrowserRouter>
          <Suspense fallback={<div className="h-full bg-bg-primary" />}>
            <Routes>
              <Route path="/" element={<MainLayout />}>
                <Route index element={<ChatPage />} />
                <Route path="mistakes" element={<MistakesPage />} />
                <Route path="exercises" element={<ExercisesPage />} />
                <Route path="kg" element={<Navigate to="/learning" replace />} />
                <Route path="learning" element={<LearningPage />} />
                <Route path="weekly" element={<WeeklyReportPage />} />
                <Route path="books" element={<SettingsPage standaloneTab="subjects" />} />
                <Route path="books/import" element={<BooksPage />} />
                <Route path="highlights" element={<HighlightPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </InspectorProvider>
    </ChatProvider>
  );
}

export default App;
