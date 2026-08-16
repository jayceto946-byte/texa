import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type InspectorPayload = {
  kind: 'source' | 'concept' | 'metadata' | 'progress' | 'detail';
  title: string;
  subtitle?: string;
  content: React.ReactNode;
};

type InspectorContextValue = {
  inspector: InspectorPayload | null;
  openInspector: (payload: InspectorPayload) => void;
  closeInspector: () => void;
};

const InspectorContext = createContext<InspectorContextValue | null>(null);

export function InspectorProvider({ children }: { children: React.ReactNode }) {
  const [inspector, setInspector] = useState<InspectorPayload | null>(null);
  const openInspector = useCallback((payload: InspectorPayload) => setInspector(payload), []);
  const closeInspector = useCallback(() => setInspector(null), []);

  useEffect(() => {
    if (!inspector) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeInspector();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [closeInspector, inspector]);

  const value = useMemo(() => ({ inspector, openInspector, closeInspector }), [closeInspector, inspector, openInspector]);
  return <InspectorContext.Provider value={value}>{children}</InspectorContext.Provider>;
}

export function useInspector() {
  const value = useContext(InspectorContext);
  if (!value) throw new Error('useInspector must be used inside InspectorProvider');
  return value;
}
