# Navigation

## App shell

Use three potential layers: persistent navigation and scope on the left, one dominant main workspace, and an optional contextual inspector on the right.

The inspector opens only for source, concept, metadata, progress detail, or another inspected object. It must be closable and must not permanently compress the main workspace.

## Sidebar

Give the sidebar four ordered regions:

1. Texa identity and collapse control.
2. Current learning scope and a clear new-session action.
3. Session history, using remaining flexible space.
4. Stable product navigation, visually lighter than the active workspace.

Do not use a dark icon rail as a second brand. Collapsed navigation should remain part of the same neutral surface system.

Use at most the necessary depth. Show the full subject, category, and textbook tree inside Library. Elsewhere show the current scope and a disclosure for switching.

## Workspace toolbar

Use one stable toolbar per route. It may contain a page or session title, compact current scope, contextual primary action, and route-specific secondary actions. Do not repeat a page title without adding orientation or action value.

## Sessions

Keep recent sessions accessible in one action. Show title, compact scope, and useful recency. Do not add decorative color bars or badges. Preserve pagination and long-history access.

Starting a new session should preserve the selected subject or textbook unless the user explicitly changes it.

## Active state

Use a low-contrast selected background, a clear text/icon color shift, and optional 1px edge emphasis. Do not combine background, thick border, glow, and bold text.

## Window behavior

- Minimum width: collapse the sidebar into a drawer or narrow neutral rail; hide the inspector.
- Normal laptop: expanded sidebar plus main workspace; inspector overlays or opens when requested.
- Wide desktop: allow sidebar, main workspace, and inspector without excessive line length.

Use CSS grid for shell columns and explicit min/max widths. Preserve the main workspace minimum width.
