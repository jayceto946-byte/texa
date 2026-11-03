import type { MouseEvent } from 'react';
import './composerMotion.css';

/** Capture clicks before file dialogs or tool actions take over focus. */
export function animateComposerTool(event: MouseEvent<HTMLElement>) {
  const button = (event.target as Element).closest<HTMLButtonElement>('button.composer-tool-button');
  if (!button || button.disabled || !event.currentTarget.contains(button) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  button.animate([
    { transform: 'scale(1)', backgroundColor: 'var(--accent-soft)' },
    { transform: 'scale(.94)', backgroundColor: 'var(--accent-soft)', offset: .35 },
    { transform: 'scale(1)', backgroundColor: getComputedStyle(button).backgroundColor },
  ], { duration: 180, easing: 'cubic-bezier(.2,.7,.2,1)' });
}
