import { readBrowserStorage } from '../../utils/browserStorage';
import type { FocusMode } from './FocusContext';
export function focusPreference(): {mode: FocusMode; minutes: number} | null {
  try { const value=JSON.parse(readBrowserStorage('localStorage','texa:focus-preference:v3') || 'null'); return value && ['countdown','stopwatch'].includes(value.mode) && Number.isInteger(value.minutes) && value.minutes>=1 && value.minutes<=120 ? value : null; } catch {return null;}
}
