# Learning flow and information architecture

## Scenes

Texa organizes around scenes, not pages. A scene is a user task context with one dominant learning goal.

- Learning scene (primary): question → learning content → evidence → follow-up.
- Library scene: manage subjects, textbooks, import, archive, selection.
- Review scene: actionable mistake and concept review.
- Exercises scene: source-backed exercise collection and focused practice.
- Settings scene: runtime health, model configuration, version, backup, advanced local controls.

Session history belongs to the Learning scene navigation. It is not a separate analytics page.

## Learning scene workflow

The Learning scene follows a study spine, not a message stream:

1. Scope: current subject / textbook / chapter context (see 00-product-model: Learning Scope).
2. Question: user poses a learning problem.
3. Learning content: explanation, derivation, example, or summary produced for the question.
4. Evidence: sources and concepts attached to the content, traceable.
5. Follow-up: further questions on the same or new scope; review and practice as next actions.

Scene transitions:
- Return to Library when the user needs to change material or scope.
- Enter Review when a mistake or review item is due.
- Enter Exercises when focused practice is the goal.

## Route responsibilities

- `/`: Learning scene, primary workspace and session resume.
- `/books`: Library. Default to the collection; import is a clear sub-mode.
- `/mistakes`: mistake capture, due review, record inspection.
- `/exercises`: exercise collection, import candidates, practice mode.
- `/learning`: actionable review plan first; activity and knowledge maintenance second.
- `/settings`: runtime, models, backup, version, advanced local configuration. Do not duplicate Library here.
- `/highlights`, `/weekly`: contextual drill-down routes reached from a named parent surface.

## Hierarchy rules

- Do not create five primary items merely because five nouns exist. Keep the frequent Learning, Review, Exercises, and Library shallow; keep Settings low in the hierarchy.
- Add a new top-level route only when the user mental model changes, not when a new object appears.
- Keep active scope and session recognizable across routes without repeating the same selector inside every page when the global selection already applies.

## Page responsibility test

A page fails when it simultaneously behaves as an import wizard, record browser, analytics dashboard, and editor without an explicit mode boundary. Separate modes with small local navigation or split view, not another top-level route.

## Principles

- Persistent context is preferred over repeated selectors and confirmation dialogs.
- Prefer predictable paths over artificially low click counts.
- Information is removed only when it is genuinely secondary.
