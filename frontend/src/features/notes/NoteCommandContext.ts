import { createContext, useContext } from 'react';
export type NoteCommandTarget = { conversationId: string; title?: string; busy?: boolean };
export const NoteCommandContext = createContext<(target: NoteCommandTarget) => void>(() => undefined);
export const useNoteCommand = () => useContext(NoteCommandContext);
