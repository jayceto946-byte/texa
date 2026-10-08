/** Browser settings may deny even evaluating window.*Storage. */
export function readBrowserStorage(kind: 'localStorage' | 'sessionStorage', key: string): string | null {
  try { return window[kind].getItem(key); } catch { return null; }
}
export function writeBrowserStorage(kind: 'localStorage' | 'sessionStorage', key: string, value: string | null): void {
  try {
    if (value === null) window[kind].removeItem(key);
    else window[kind].setItem(key, value);
  } catch { /* Optional persistence; credentials remain in current page memory. */ }
}
