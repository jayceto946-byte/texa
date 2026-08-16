# Information architecture

## User mental model

Organize Texa around:

1. Workspace: current session, question, answer, composer, and active learning scope.
2. Library: subject, category, textbook, textbook role, import, archive, and selection.
3. Review: actionable mistake and concept review, with progress as supporting evidence.
4. Exercises: source-backed exercise library and focused practice.
5. Settings: runtime health, model configuration, version, backup, and advanced system controls.

Session history belongs to Workspace navigation. It is not a separate analytics page.

## Recommended route responsibilities

- `/`: primary learning workspace and session resume.
- `/books`: Library. Default to the collection; make import a clear sub-mode.
- `/mistakes`: mistake capture, due review, and record inspection.
- `/exercises`: exercise collection, import candidates, and practice mode.
- `/learning`: actionable review plan first; activity and knowledge maintenance second.
- `/settings`: runtime, models, backup, version, and advanced local configuration. Do not duplicate Library here.
- `/highlights` and `/weekly`: contextual drill-down routes, reached from a named parent surface.

Do not create five primary items merely because five nouns exist. Keep the frequent workspace, review, exercises, and library shallow. Keep settings low in the hierarchy.

## Persistent objects

Keep active subject and textbook group, active session in Workspace, and task-affecting runtime degradation recognizable across routes.

Do not repeat the same scope selector independently inside every page if the global selection already applies.

## Page responsibility test

A page fails when it simultaneously behaves as an import wizard, record browser, analytics dashboard, and editor without an explicit mode boundary. Separate modes with small local navigation or split view, not another top-level route unless the mental model changes.

## Backend boundary

Map the new IA onto existing APIs. Do not rename backend modules to mirror navigation. Record `UX_BLOCKED_BY_BACKEND` only when a user-visible object cannot be represented with existing data.
