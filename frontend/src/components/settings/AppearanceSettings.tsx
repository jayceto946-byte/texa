import { Check } from 'lucide-react';
import { useState } from 'react';
import { applyTexaTheme, readStoredTexaTheme, TEXA_THEMES, type TexaThemeId } from '../../theme';

export default function AppearanceSettings() {
  const [themeId, setThemeId] = useState<TexaThemeId>(() => readStoredTexaTheme());

  const selectTheme = (nextThemeId: TexaThemeId) => {
    applyTexaTheme(nextThemeId);
    setThemeId(nextThemeId);
  };

  return (
    <section aria-labelledby="appearance-theme-heading" className="settings-section">
      <div>
        <h4 id="appearance-theme-heading" className="settings-section-title">主题色</h4>
        <p className="mt-1 settings-secondary">选择后立即应用，并保存在当前设备。</p>
      </div>
      <div className="appearance-theme-list" role="radiogroup" aria-label="主题色">
        {TEXA_THEMES.map((theme) => {
          const active = theme.id === themeId;
          const swatches = [
            theme.tokens['--color-bg-primary'],
            theme.tokens['--color-bg-card'],
            theme.tokens['--color-accent'],
            theme.tokens['--color-text-primary'],
          ];
          return (
            <button
              key={theme.id}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => selectTheme(theme.id)}
              className={`appearance-theme-option ${active ? 'is-active' : ''}`}
            >
              <span className="appearance-theme-copy">
                <span className="appearance-theme-name">{theme.label}</span>
                <span className="appearance-theme-description">{theme.description}</span>
              </span>
              <span className="appearance-theme-swatches" aria-hidden="true">
                {swatches.map((color, index) => <span key={`${theme.id}-${index}`} style={{ backgroundColor: color }} />)}
              </span>
              <span className="appearance-theme-state" aria-hidden="true">{active && <Check />}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
