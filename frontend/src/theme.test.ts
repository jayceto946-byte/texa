import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import {
  applyTexaTheme,
  DEFAULT_TEXA_THEME,
  isTexaThemeId,
  readStoredTexaTheme,
  TEXA_THEMES,
  TEXA_THEME_STORAGE_KEY,
} from './theme';
const css = readFileSync(new URL('./index.css', import.meta.url), 'utf8');

function luminance(hex: string) {
  const rgb = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const linear = rgb.map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

function contrast(a: string, b: string) {
  const values = [luminance(a), luminance(b)].sort((left, right) => right - left);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

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

  it('keeps supporting text legible across the existing themes', () => {
    for (const theme of TEXA_THEMES) {
      const supportingText = theme.tokens['--color-text-tertiary'];
      for (const surface of ['--color-bg-primary', '--color-bg-secondary', '--color-bg-card'] as const) {
        expect(contrast(supportingText, theme.tokens[surface]), `${theme.id} on ${surface}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it('keeps initial mineral colors in sync with the runtime registry', () => {
    const initialColors = css.slice(css.indexOf('@theme {'), css.indexOf('}', css.indexOf('@theme {')));
    for (const [name, value] of Object.entries(TEXA_THEMES[0].tokens)) {
      if (name.startsWith('--color-')) expect(initialColors).toContain(`${name}: ${value};`);
    }
  });
});
