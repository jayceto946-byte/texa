import { createContext, useContext } from 'react';
export type FocusTask = {
    id: string;
    goal_id: string;
    title: string;
    content: string;
    duration_seconds: number;
    elapsed_seconds: number;
    status: string;
    revision: number;
};
export type FocusSnapshot = {
    revision: number;
    tasks: FocusTask[];
    current_task: FocusTask | null;
    status: string;
    remaining_seconds: number;
    server_time: number;
};
export type FocusCommand = {
    operation: 'create' | 'start' | 'switch' | 'pause' | 'finish' | 'complete';
    goal_id?: string;
    task_id?: string;
    title?: string;
    content?: string;
    duration_seconds?: number;
};
export const FocusContext = createContext<{
    data: FocusSnapshot | null;
    busy: boolean;
    error: string;
    pending: boolean;
    remaining: number;
    refresh: () => Promise<void>;
    command: (value: FocusCommand) => Promise<void>;
    reconcile: () => Promise<void>;
} | null>(null);
export function useFocus() { const value = useContext(FocusContext); if (!value)
    throw new Error('Focus provider missing'); return value; }
export function focusTime(seconds: number) { const value = Math.max(0, Math.ceil(seconds)); return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`; }
