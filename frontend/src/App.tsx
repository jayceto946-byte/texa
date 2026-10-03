import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ChatProvider } from './contexts/ChatContext';
import MainLayout from './layouts/MainLayout';
import DesktopTitleBar from './components/DesktopTitleBar';
import FirstRunGuide from './components/FirstRunGuide';
import { InspectorProvider } from './contexts/InspectorContext';
import GoalsPage from './pages/GoalsPage';
import NotesPage from './pages/NotesPage';
import NoteDetailPage from './pages/NoteDetailPage';
import NoteDraftPage from './pages/NoteDraftPage';
import ChatPage from './pages/ChatPage';
import MistakesPage from './pages/MistakesPage';
import { MistakeDetailPage, MistakeDiagnosisPage } from './pages/MistakesPage';
import MistakeIntakePage from './pages/MistakeIntakePage';
import ExercisesPage from './pages/ExercisesPage';
import BooksPage from './pages/BooksPage';
import HighlightPage from './pages/HighlightPage';
import LearningPage from './pages/LearningPage';
import ReviewSessionPage from './pages/ReviewSessionPage';
import WeeklyReportPage from './pages/WeeklyReportPage';
import SettingsPage from './components/SystemHealth';

function App() {
  return (
    <ChatProvider>
      <InspectorProvider>
        <DesktopTitleBar />
        <BrowserRouter>
          <FirstRunGuide>
          <Routes>
            <Route path="/" element={<MainLayout />}>
              <Route index element={<ChatPage />} />
              <Route path="goals" element={<GoalsPage />} />
              <Route path="notes" element={<NotesPage />} />
              <Route path="notes/drafts/:draftId" element={<NoteDraftPage />} />
              <Route path="notes/:noteId" element={<NoteDetailPage />} />
              <Route path="mistakes" element={<MistakesPage />} />
              <Route path="mistakes/diagnosis" element={<MistakeDiagnosisPage />} />
              <Route path="mistakes/intake" element={<MistakeIntakePage />} />
              <Route path="mistakes/intake/:draftId" element={<MistakeIntakePage />} />
              <Route path="mistakes/review" element={<Navigate to="/learning/review" replace />} />
              <Route path="mistakes/:id" element={<MistakeDetailPage />} />
              <Route path="exercises" element={<ExercisesPage />} />
              <Route path="kg" element={<Navigate to="/learning" replace />} />
              <Route path="learning" element={<LearningPage />} />
              <Route path="learning/review" element={<ReviewSessionPage />} />
              <Route path="learning/review/:sessionId" element={<ReviewSessionPage />} />
              <Route path="weekly" element={<WeeklyReportPage />} />
              <Route path="books" element={<SettingsPage standaloneTab="subjects" />} />
              <Route path="books/import" element={<BooksPage />} />
              <Route path="highlights" element={<HighlightPage />} />
              <Route path="settings" element={<Navigate to="/" replace state={{ openSettings: true }} />} />
            </Route>
          </Routes>
          </FirstRunGuide>
        </BrowserRouter>
      </InspectorProvider>
    </ChatProvider>
  );
}

export default App;
