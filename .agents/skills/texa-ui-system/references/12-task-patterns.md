# Task patterns

## Purpose

Agent tasks are concrete, not "design Texa": modify the textbook page, optimize the question/answer page, add a mistake feature, add a new learning entry. This file gives the standard procedure for such tasks.

## Standard procedure

When adding or modifying UI:

1. Identify the user learning goal — which learning task is served, in which scene (01-learning-flow.md).
2. Identify the existing product object — map the task to an object in 00-product-model.md.
3. Choose the correct surface — pick the context region layout from 02-page-layout.md.
4. Decide disclosure level — place primary content on the surface, secondary content in disclosure or inspector (03-learning-canvas.md, 05-interaction.md).
5. Implement without breaking existing contracts — keep QA streaming, Markdown, LaTeX, citations, typed repair, and business hooks intact.

Anti-pattern anchor: adding a feature is not adding a card. New functionality maps to an existing object and surface before any new presentation is introduced.

## Common task templates

### Modify textbook page

- Learning goal: select and manage learning material.
- Object: Textbook; Learning Scope when the page affects current scope.
- Surface: Library scene (01, 02); import remains a nested sub-mode.
- Check: role semantics at user level only; never surface backend fields.

### Optimize question/answer page

- Learning goal: obtain an explanation for a problem.
- Objects: Question, Answer, Source, Concept.
- Surface: Learning scene, Learning Canvas (03).
- Check: answer stays a document flow, not a chat card; sources/concepts progressively disclosed.

### Add mistake feature

- Learning goal: attribute and review a mistake.
- Objects: Mistake, ReviewItem.
- Surface: Review scene; list + detail.
- Check: review queue is perceivable and actionable; progress only when it changes the next action.

### Add a new learning entry

- Decide first whether it is a new scene or a new entry into an existing scene.
- Prefer reusing an existing scene and surface.
- Add a new route only when the user mental model changes (01).
- Check: the new entry never compresses the workspace or duplicates scope/session context.

## Ordering

Prefer structural correction before visual polish. Reuse existing business logic and feature hooks; add primitives only when they will be reused.
