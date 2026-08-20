# States

## Principle

Status informs, does not decorate. Expose a technical state only when it affects a user decision.

## User-perceivable states

Define states at the user-experience layer, not by backend pipeline:

- **idle**: no indicator; readiness shown only when it matters.
- **loading**: object being loaded; short requests avoid spinner flicker.
- **generating**: content is being produced; expressed inside the content area without covering already-generated content.
- **repair required**: resources need repair; globally visible with progress, retry, and logs.
- **error**: state what failed, what remains safe, and the next action.
- **offline**: distinguish local service unavailable from external model unavailable.
- **empty**: state what is absent and the single task that populates it.

## State presentation

- **loading**: one spinner within an active control only when progress is unavailable; skeletons only when they preserve final layout and the delay justifies them; determinate progress only for real measurable work; never decorative shimmer.
- **generating**: stage indicators stay inside the active content flow and never overwrite already-generated body content.
- **repair required**: the repair entry, repair progress, retry, and logs stay discoverable; do not place the only repair action behind advanced settings.
- **error**: keep distinct explanations for different causes (e.g., missing resources, corrupt or incompatible resources, import failure, tokenizer mismatch). Never collapse them into one generic error.
- **empty**: use task language such as `尚未添加教材。添加教材后可以建立学习上下文。` No welcome marketing, slogans, illustrations, sparkles, or a grid of feature cards.
