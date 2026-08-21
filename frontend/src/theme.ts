export const TEXA_THEME_STORAGE_KEY = 'texa_appearance_theme';

export type TexaThemeId = 'mineral' | 'graphite' | 'clay' | 'notebook' | 'codex';

type ThemeTokens = Record<`--${string}`, string>;

export type TexaTheme = {
  id: TexaThemeId;
  label: string;
  description: string;
  tokens: ThemeTokens;
};

export const TEXA_THEMES: readonly TexaTheme[] = [
  {
    id: 'mineral',
    label: '矿物',
    description: '冷中性灰与低饱和深绿，适合长时间阅读。',
    tokens: {
      '--color-bg-primary': '#f2f4f1',
      '--color-bg-secondary': '#ecefea',
      '--color-bg-card': '#fbfcfa',
      '--color-text-primary': '#232825',
      '--color-text-secondary': '#626b65',
      '--color-text-tertiary': '#858e88',
      '--color-accent': '#35695a',
      '--color-accent-hover': '#285448',
      '--color-border': '#d7ddd7',
      '--surface-raised': '#fbfcfa',
      '--surface-muted': '#eef1ed',
      '--surface-subtle': '#f6f8f5',
      '--surface-black': '#29312d',
      '--surface-tile': '#e5e9e4',
      '--text-muted': '#737d76',
      '--accent-muted': 'rgba(53, 105, 90, 0.13)',
      '--accent-soft': 'rgba(53, 105, 90, 0.095)',
      '--accent-softer': 'rgba(53, 105, 90, 0.055)',
      '--info': '#35695a',
      '--scrollbar-thumb': '#c8cec9',
      '--scrollbar-thumb-hover': '#9da69f',
      '--heat-0-bg': '#f0f2ef',
      '--heat-0-border': '#dfe4df',
      '--heat-1-bg': '#dce9e2',
      '--heat-1-border': '#c3d9cc',
      '--heat-2-bg': '#a9c9b9',
      '--heat-2-border': '#86b29d',
      '--heat-3-bg': '#5f927f',
      '--heat-3-border': '#497766',
      '--heat-4-bg': '#35695a',
      '--heat-4-border': '#285448',
    },
  },
  {
    id: 'graphite',
    label: '石墨',
    description: '近单色中性灰，减少主题色对内容的干扰。',
    tokens: {
      '--color-bg-primary': '#f2f3f3',
      '--color-bg-secondary': '#eceeee',
      '--color-bg-card': '#fbfbfa',
      '--color-text-primary': '#222625',
      '--color-text-secondary': '#646b69',
      '--color-text-tertiary': '#888f8d',
      '--color-accent': '#4c5d59',
      '--color-accent-hover': '#374743',
      '--color-border': '#d6dad8',
      '--surface-raised': '#fbfbfa',
      '--surface-muted': '#eef0ef',
      '--surface-subtle': '#f7f8f7',
      '--surface-black': '#272c2b',
      '--surface-tile': '#e5e8e7',
      '--text-muted': '#747c79',
      '--accent-muted': 'rgba(76, 93, 89, 0.13)',
      '--accent-soft': 'rgba(76, 93, 89, 0.095)',
      '--accent-softer': 'rgba(76, 93, 89, 0.055)',
      '--info': '#4c5d59',
      '--scrollbar-thumb': '#c7ccca',
      '--scrollbar-thumb-hover': '#9ba29f',
      '--heat-0-bg': '#eff1f0',
      '--heat-0-border': '#dde1df',
      '--heat-1-bg': '#dfe4e2',
      '--heat-1-border': '#cbd2cf',
      '--heat-2-bg': '#b7c1bd',
      '--heat-2-border': '#9ca9a4',
      '--heat-3-bg': '#788983',
      '--heat-3-border': '#64756f',
      '--heat-4-bg': '#4c5d59',
      '--heat-4-border': '#374743',
    },
  },
  {
    id: 'clay',
    label: '陶土',
    description: '暖灰与氧化红，增强操作层次但保持克制。',
    tokens: {
      '--color-bg-primary': '#f4f2ef',
      '--color-bg-secondary': '#eeeae6',
      '--color-bg-card': '#fdfcf9',
      '--color-text-primary': '#2c2927',
      '--color-text-secondary': '#6c6560',
      '--color-text-tertiary': '#918983',
      '--color-accent': '#8a5142',
      '--color-accent-hover': '#713f34',
      '--color-border': '#ddd6d0',
      '--surface-raised': '#fdfcf9',
      '--surface-muted': '#f0ece8',
      '--surface-subtle': '#f8f5f2',
      '--surface-black': '#332d2a',
      '--surface-tile': '#e9e3de',
      '--text-muted': '#7c746e',
      '--accent-muted': 'rgba(138, 81, 66, 0.13)',
      '--accent-soft': 'rgba(138, 81, 66, 0.095)',
      '--accent-softer': 'rgba(138, 81, 66, 0.055)',
      '--info': '#8a5142',
      '--scrollbar-thumb': '#cec6c0',
      '--scrollbar-thumb-hover': '#a79d96',
      '--heat-0-bg': '#f1eeeb',
      '--heat-0-border': '#e2dcd7',
      '--heat-1-bg': '#eadbd5',
      '--heat-1-border': '#d9c1b8',
      '--heat-2-bg': '#d2aaa0',
      '--heat-2-border': '#bd897c',
      '--heat-3-bg': '#a96a59',
      '--heat-3-border': '#925645',
      '--heat-4-bg': '#8a5142',
      '--heat-4-border': '#713f34',
    },
  },
  {
    id: 'notebook',
    label: '记事本',
    description: '温和纸面、墨色正文与暗金标记，适合笔记式阅读。',
    tokens: {
      '--color-bg-primary': '#f4f1e8',
      '--color-bg-secondary': '#ebe6d8',
      '--color-bg-card': '#fffdf7',
      '--color-text-primary': '#28261f',
      '--color-text-secondary': '#696457',
      '--color-text-tertiary': '#918a79',
      '--color-accent': '#765713',
      '--color-accent-hover': '#5d430d',
      '--color-border': '#dbd4c2',
      '--surface-raised': '#fffdf7',
      '--surface-muted': '#efeadf',
      '--surface-subtle': '#f9f6ee',
      '--surface-black': '#302e27',
      '--surface-tile': '#e6dfcf',
      '--text-muted': '#797262',
      '--accent-muted': 'rgba(118, 87, 19, 0.14)',
      '--accent-soft': 'rgba(118, 87, 19, 0.10)',
      '--accent-softer': 'rgba(118, 87, 19, 0.06)',
      '--info': '#765713',
      '--scrollbar-thumb': '#c9c1ae',
      '--scrollbar-thumb-hover': '#a59b85',
      '--heat-0-bg': '#f0ece2',
      '--heat-0-border': '#ded7c7',
      '--heat-1-bg': '#e9dfc3',
      '--heat-1-border': '#d8c99d',
      '--heat-2-bg': '#cfb56e',
      '--heat-2-border': '#b99c4d',
      '--heat-3-bg': '#9e7927',
      '--heat-3-border': '#86641b',
      '--heat-4-bg': '#765713',
      '--heat-4-border': '#5d430d',
    },
  },
  {
    id: 'codex',
    label: '灰白黑',
    description: '克制灰阶与黑色操作信号，突出壳层和内容分区。',
    tokens: {
      '--color-bg-primary': '#f7f7f5',
      '--color-bg-secondary': '#eeeeeb',
      '--color-bg-card': '#ffffff',
      '--color-text-primary': '#242422',
      '--color-text-secondary': '#656561',
      '--color-text-tertiary': '#90908a',
      '--color-accent': '#30302e',
      '--color-accent-hover': '#171716',
      '--color-border': '#ddddda',
      '--surface-raised': '#ffffff',
      '--surface-muted': '#efefec',
      '--surface-subtle': '#f8f8f6',
      '--surface-black': '#242422',
      '--surface-tile': '#e6e6e2',
      '--text-muted': '#74746f',
      '--accent-muted': 'rgba(48, 48, 46, 0.11)',
      '--accent-soft': 'rgba(48, 48, 46, 0.075)',
      '--accent-softer': 'rgba(48, 48, 46, 0.045)',
      '--info': '#4f4f4b',
      '--scrollbar-thumb': '#c9c9c4',
      '--scrollbar-thumb-hover': '#9f9f99',
      '--heat-0-bg': '#f0f0ed',
      '--heat-0-border': '#dfdfda',
      '--heat-1-bg': '#e1e1dc',
      '--heat-1-border': '#cdcdc7',
      '--heat-2-bg': '#b8b8b1',
      '--heat-2-border': '#9d9d96',
      '--heat-3-bg': '#74746e',
      '--heat-3-border': '#5d5d58',
      '--heat-4-bg': '#30302e',
      '--heat-4-border': '#171716',
    },
  },
] as const;

export const DEFAULT_TEXA_THEME: TexaThemeId = 'mineral';

export function isTexaThemeId(value: string | null | undefined): value is TexaThemeId {
  return TEXA_THEMES.some((theme) => theme.id === value);
}

export function readStoredTexaTheme(storage: Pick<Storage, 'getItem'> = window.localStorage): TexaThemeId {
  try {
    const value = storage.getItem(TEXA_THEME_STORAGE_KEY);
    return isTexaThemeId(value) ? value : DEFAULT_TEXA_THEME;
  } catch {
    return DEFAULT_TEXA_THEME;
  }
}

export function applyTexaTheme(
  id: TexaThemeId,
  root: Pick<HTMLElement, 'dataset' | 'style'> = document.documentElement,
  storage: Pick<Storage, 'setItem'> = window.localStorage,
) {
  const theme = TEXA_THEMES.find((candidate) => candidate.id === id) || TEXA_THEMES[0];
  root.dataset.theme = theme.id;
  for (const [token, value] of Object.entries(theme.tokens)) root.style.setProperty(token, value);
  try {
    storage.setItem(TEXA_THEME_STORAGE_KEY, theme.id);
  } catch {
    // The theme still applies for this session when storage is unavailable.
  }
  return theme.id;
}

export function initializeTexaTheme() {
  return applyTexaTheme(readStoredTexaTheme());
}
