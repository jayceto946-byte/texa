# Color

## Direction

Use neutral surfaces with one restrained theme accent. The default Mineral theme uses cool-neutral surfaces and a low-saturation deep green. Graphite and Clay provide neutral and warm alternatives; Notebook adds warm paper-and-ink reading surfaces, while Codex-inspired Grayscale uses gray-white-black shell separation. Neutral dominates; accent guides; status colors communicate real state.

Reference products are directional, not palettes to copy. Notebook borrows the document hierarchy and calm reading atmosphere associated with note-taking tools, without ruled-paper decoration or faux stationery. Codex-inspired Grayscale borrows restrained shell contrast, dense navigation, and quiet selection states, without copying another product's exact values, identity, or layout.

## Semantic tokens

Define background, surface, surface-subtle, foreground, muted, border, accent, accent-muted, success, warning, and error. Consume tokens by meaning, not raw color name.

Do not hardcode a named brand color into components. Consume the active theme's accent tokens, and do not apply accent to every icon, heading, and border.

## Status rules

- Pair color with icon and text.
- Reserve green for actual ready or success.
- Reserve amber for actionable degradation or pending repair.
- Reserve red for failure or destructive action.
- Do not give every metadata label a unique color.

## Themes

Theme switching is user preference, not page decoration. Every theme maps the same semantic tokens, uses one accent family, and preserves hierarchy, contrast, status meaning, and reading comfort. Store the selected theme locally and apply it at application startup. Add themes through the shared registry rather than component-specific overrides.

Current light themes:

- Mineral: cool neutral + low-saturation deep green; default for long reading sessions.
- Graphite: near-monochrome neutral; minimizes chromatic distraction.
- Clay: warm neutral + restrained oxide red; increases interaction distinction without becoming decorative.
- Notebook: warm paper-and-ink neutrals + dark gold; supports note-like reading without stationery decoration.
- Codex-inspired Grayscale: gray-white-black shell separation; prioritizes structure and quiet selection over brand color.

If a dark theme is added later, map the same semantic tokens and verify hierarchy independently rather than mechanically inverting colors.

## Prohibited

No purple gradient, gradient text, neon, rainbow status colors, large accent backgrounds, decorative color blocks, or pure black sidebar that competes with the workspace.
