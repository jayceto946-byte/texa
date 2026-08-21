import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ChatProvider } from './contexts/ChatContext';
import MainLayout from './layouts/MainLayout';
import DesktopTitleBar from './components/DesktopTitleBar';
import FirstRunGuide from './components/FirstRunGuide';
import { InspectorProvider } from './contexts/InspectorContext';
import ChatPage from './pages/ChatPage';
import MistakesPage from './pages/MistakesPage';
import ExercisesPage from './pages/ExercisesPage';
import BooksPage from './pages/BooksPage';
import HighlightPage from './pages/HighlightPage';
import LearningPage from './pages/LearningPage';
import WeeklyReportPage from './pages/WeeklyReportPage';
import SettingsPage from './components/SystemHealth';

function App() {
  return (
    <ChatProvider>
      <InspectorProvider>
        <DesktopTitleBar />
        <FirstRunGuide />
        <BrowserRouter>
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
        </BrowserRouter>
      </InspectorProvider>
    </ChatProvider>
  );
}

export default App;
