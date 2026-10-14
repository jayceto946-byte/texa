export {};
declare global {
  interface Window {
    texaStartup?: {
      mark: (stage: string) => void;
      ready: () => void;
      fail: (stage: string, error?: unknown, resource?: string) => void;
    };
  }
}
