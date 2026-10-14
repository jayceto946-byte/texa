import { isRemoteBrowser } from './api/client';

// Mark remote before dynamic CSS loads, avoiding large desktop font downloads.
if (isRemoteBrowser()) document.documentElement.dataset.texaRemote = 'true';

if (new URLSearchParams(window.location.search).get('texa_perf') === '1') {
  void import('./utils/mobilePerformance').then(({ installMobilePerformance }) => installMobilePerformance()).catch(() => { /* Diagnostics must not block learning. */ });
}

window.texaStartup?.mark('entry-loaded');

// Keep app module evaluation inside a caught import, after the HTML guard.
void import('./bootstrap').then(({ bootApp }) => bootApp()).catch((error: unknown) => {
  window.texaStartup?.fail('module-init', error);
});
