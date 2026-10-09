import { expect, it } from 'vitest';
import { resourceCategory } from './mobilePerformance';

it('exports fixed categories instead of private resource or session identities', () => {
  expect(resourceCategory('/api/chat/conversations/private-session/messages')).toBe('session-read');
  expect(resourceCategory('/api/books/private-book/pdf')).toBe('textbook-pdf');
  expect(resourceCategory('/assets/HarmonyOS_Sans_SC_Regular-hash.ttf')).toBe('harmony-font');
  expect(resourceCategory('/api/mistakes/visual-tasks/private-task/image')).toBe('image');
});
