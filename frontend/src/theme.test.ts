import { describe, expect, it } from 'vitest';
import {
  applyTexaTheme,
  DEFAULT_TEXA_THEME,
  isTexaThemeId,
  readStoredTexaTheme,
  TEXA_THEMES,
  TEXA_THEME_STORAGE_KEY,
} from './theme';

describe('Texa appearance themes', () => {
  it('keeps a complete, unique theme registry', () => {
    expect(TEXA_THEMES.map((theme) => theme.id)).toEqual([
      'mineral',
      'graphite',
      'clay',
      'notebook',
      'codex',
    ]);
    expect(new Set(TEXA_THEMES.flatMap((theme) => Object.keys(theme.tokens))).size).toBe(
      Object.keys(TEXA_THEMES[0].tokens).length,
    );
    for (const theme of TEXA_THEMES) {
      expect(Object.keys(theme.tokens)).toEqual(Object.keys(TEXA_THEMES[0].tokens));
    }
  });

  it('falls back from unknown stored values', () => {
    expect(readStoredTexaTheme({ getItem: () => 'unknown' })).toBe(DEFAULT_TEXA_THEME);
    expect(isTexaThemeId('graphite')).toBe(true);
    expect(isTexaThemeId('notebook')).toBe(true);
    expect(isTexaThemeId('codex')).toBe(true);
    expect(isTexaThemeId('blue')).toBe(false);
  });

  it('applies semantic tokens and persists the selection', () => {
    const values = new Map<string, string>();
    const root = {
      dataset: {} as DOMStringMap,
      style: {
        setProperty: (name: string, value: string) => { values.set(name, value); },
      } as unknown as CSSStyleDeclaration,
    };
    const storage = { setItem: (name: string, value: string) => values.set(name, value) };

    expect(applyTexaTheme('clay', root, storage)).toBe('clay');
    expect(root.dataset.theme).toBe('clay');
    expect(values.get('--color-accent')).toBe('#8a5142');
    expect(values.get(TEXA_THEME_STORAGE_KEY)).toBe('clay');
  });
});
