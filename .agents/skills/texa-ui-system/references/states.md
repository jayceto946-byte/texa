# States

## Principle

Status should inform, not decorate. Match the state surface to task duration and consequence.

## Required states

- loading: delay for very short requests; otherwise show the object being loaded
- ready: usually implicit; show only when readiness matters
- indexing: show textbook, current phase, and real progress when available
- retrieving: show a compact stage inside the active answer flow
- repairing: show typed cause, current repair phase, progress, and cancel or retry rules
- error: state what failed, what remains safe, and the next action
- offline: distinguish local service unavailable from external model unavailable
- empty: state what is absent and the single task that populates it

## ONNX typed failure invariant

Preserve `MODEL_MISSING`, `MODEL_CORRUPT_OR_INCOMPATIBLE`, `ORT_IMPORT_FAILURE`, and `TOKENIZER_MISMATCH` as distinct explanations. Never collapse them into a generic model error. Keep repair, repair progress, retry, and logs discoverable. Do not place the only repair action behind advanced settings.

## Loading rules

- Avoid spinner flicker for short requests.
- Use one spinner within an active control only when progress is unavailable.
- Use skeletons only when they preserve final layout and the delay justifies them.
- Use determinate progress only for real measurable work.
- Never use decorative shimmer.

## Empty states

Use task language such as: `尚未添加教材。添加教材后可以建立学习上下文。`

Do not use welcome marketing, slogans, illustrations, sparkles, or a grid of feature cards.
