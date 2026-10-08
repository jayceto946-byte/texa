import './shell.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { initializeTexaTheme } from './theme';
import StartupBoundary from './components/StartupBoundary';

export function bootApp() {
  window.texaStartup?.mark('theme-start');
  initializeTexaTheme();
  window.texaStartup?.mark('theme-applied');
  const root = document.getElementById('root');
  if (!root) throw new Error('Missing root');
  createRoot(root).render(<StrictMode><StartupBoundary><App /></StartupBoundary></StrictMode>);
}
