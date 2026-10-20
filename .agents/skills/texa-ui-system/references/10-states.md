# States

State labels describe what happened, the consequence, and a useful next action. Do not imply success while work is pending or an answer is unverified.

- Loading and generating belong to the active content or control. Do not replace already-generated text with a stage label.
- Empty states explain what is absent and how to begin, with a consistent title, supporting text, and action scale. Their placement can fit the page.
- Errors and repair states distinguish causes when recovery differs. Keep retry, progress, and diagnostic detail available.
- Selected, pressed, focus, and disabled states must be perceivable without hover or color alone. Keep keyboard focus visible without doubled rings.

Component markup and styles are the authority for exact presentation and interaction.

## Input tools and command menus

For tools inside a bordered composer, prefer a quiet fill for enabled hover/selected states when another border adds no useful grouping. Keep the focus outline. Disabled tools must not gain an enabled hover treatment; pending generation should leave the stop action identifiable. This is a local pattern, not a ban on borders inside forms.

For a command menu, design the keyboard path with the open state: Enter/Space or ArrowDown enters at the first enabled item, ArrowUp enters at the last; arrows and Home/End move among enabled items. Escape returns to the trigger; Tab/Shift+Tab exits and dismisses. Outside clicks dismiss without stealing focus. Give the trigger an expanded state and controls relationship, and name the menu for its actual commands. Selection groups and text editors retain their own keyboard contracts.

For question inputs, preserve IME confirmation and Shift+Enter before tuning visual feedback. Test native composition and keyCode 229 separately from normal Enter. Label synthetic event checks separately from an actual OS candidate-window check; a Chinese paste does not prove IME correctness.

These refinements come from the Composer trial and its before/after rendered checks in [the source study](../../../../docs/design/claude-ui-source-study-2026-10-19.md). Keep existing backend task, approval and receipt states authoritative; a polished loading/success animation must not invent completion.
