# Texa frontend

React + Vite desktop learning workspace. The Electron shell in `../desktop/` is the primary delivery path.

## Development

```sh
npm install
npm run dev
npm run lint
npm run test
npm run build
```

Run `npm run dev` from `../desktop/` to inspect the integrated Electron app. Frontend-only preview cannot verify native titlebar and window behavior.

## UI system

- Theme identities and semantic colors: `src/theme.ts`.
- Initial mineral fallback, typography, spacing, density, radius, motion, and shared control styles: `src/index.css`.
- Shared dialog, select, inspector, and async state components: `src/components/ui/`.
- Product principles and review questions: `../.agents/skills/texa-ui-system/SKILL.md`.

Shared page and component styling applies to both Windows and macOS. Platform-specific selectors are reserved for native window controls, titlebar, drag regions, and system font fallback.
