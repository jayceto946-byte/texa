# Page layout

## Context Region model

Texa uses persistent context regions, not a fixed layout. There is no mandated three-column structure.

Possible combinations:

- Workspace only.
- Workspace + Inspector.
- Context sidebar + Workspace.
- Context sidebar + Workspace + Inspector.

Layout choice is based on:
- the user task,
- information priority,
- the current learning scene.

Avoid adding regions just to keep a fixed column count.

## Regions

### Workspace

- Always present; carries the dominant learning task.
- Must stay dominant, predictable, and above a minimum usable width.
- Do not permanently compress it to satisfy a column count.

### Context sidebar

- Exists when scope, session history, and scene navigation add value to the current task.
- Handled as a page region, not as a generic reusable component (see 04-components.md scope).
- Expandable and collapsible; collapses to a drawer on narrow windows.

### Inspector

- Opens only for an inspected object (source, concept, metadata, progress detail).
- Must be closable.
- Must not permanently compress the workspace.

### Toolbar

- One stable toolbar per route.
- Contains page or session title, compact current scope, contextual primary action, and route-specific secondary actions.
- Do not repeat a page title without adding orientation or action value.

## Active state

Use a low-contrast selected background, a clear text/icon color shift, and optional 1px edge emphasis. Do not combine background, thick border, glow, and bold text.

## Responsive behavior

- Minimum window: primary action remains usable and the Composer visible; context sidebar collapses into a drawer; inspector hidden.
- Below about 920px: drawer navigation and overlay inspector.
- Normal laptop: avoid three permanently visible regions.
- Wide widths: add useful context, not empty margins.

Region widths (constraints, not fixed values):
- Context sidebar expanded: 272–304px.
- Collapsed navigation: 52–60px.
- Inspector: 320–400px, never below 300px.
- Reading column: 720–880px depending on math and tables (see 03-learning-canvas.md).

Use CSS grid for shell columns and explicit min/max widths. Preserve the workspace minimum width.

## Page contracts

Per route: primary task, dominant action, layout form, allowed regions, minimum width.

| Route | Primary task | Dominant action | Layout form | Allowed regions | Notes |
|---|---|---|---|---|---|
| `/` | Learn within current scope | Submit question / follow up | Learning Canvas, document flow | Sidebar + Workspace + Inspector | Canvas is the dominant region |
| `/books` | Manage learning material | Import / select textbook | List + detail split view | Sidebar + Workspace | Import is a nested sub-mode |
| `/mistakes` | Capture and review mistakes | Open due review | List + detail | Sidebar + Workspace | Inspector optional |
| `/exercises` | Practice from traceable sources | Start practice | Collection list + practice mode | Sidebar + Workspace | Practice mode has explicit boundary |
| `/learning` | Act on review plan | Start due review | Actionable list first | Sidebar + Workspace | Activity/secondary content lower |
| `/settings` | Configure runtime | Save / repair | Form-like single column | Workspace | Low in hierarchy; no Library duplicate |

Rules:
- Do not wrap a split view in a card and then wrap every row in another card.
- Surfaces are added only when spacing and dividers cannot express separation (see 09-surfaces.md).
