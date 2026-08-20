# Components

## Scope

Reusable UI controls. The context sidebar is handled as a page region (see 02-page-layout.md), not as a generic component. The Learning Canvas is a content surface (see 03-learning-canvas.md), not a component here.

## Button

Variants: primary, secondary, ghost, danger, icon.

- Each page normally has one dominant primary action.
- Disable only when the user can understand why.
- Use semantic button elements.

## Menu / OverflowMenu

- Carries low-frequency actions (attachments, math input extras, reports, secondary tools).
- Trigger toggles open/closed.
- Dismiss on outside pointer down (capture phase).
- Escape closes the menu and returns focus to the trigger.
- Menu items close the menu before executing.

## Composer

- Stable bottom location; input focus visually clear.
- Send is the single dominant action.
- Attachment and math input available without a floating pill or icon crowd.
- Reserve an extension point for image input without pretending unavailable features exist.
- Preserve the established submit shortcut and multiline behavior.
- The Composer surface owns border, background, radius, and focus ring; the textarea itself stays transparent/borderless.

## Inspector

- Opens for an inspected object: source, concept, metadata, progress detail.
- Closable; Escape closes it.
- Must not permanently compress the workspace.

## Disclosure

- Used for: source detail, concept detail, metadata, advanced settings, archived items, long technical logs.
- Never used for: current scope, active repair, primary action.

## Reuse rule

- Reuse existing business logic and feature hooks before adding components.
- Add a primitive only when it will be reused.
- Use semantic button, link, input, and heading elements.
