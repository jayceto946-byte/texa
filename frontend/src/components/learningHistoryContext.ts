import { createContext } from 'react';

export const LearningHistoryContext = createContext<{ visible: boolean; close: () => void; onMenuOpenChange: (open: boolean, id: string) => void }>({
  visible: true,
  close: () => {},
  onMenuOpenChange: () => {},
});
