---
name: texa-ui-system
description: Use this skill whenever designing, implementing, reviewing, or modifying Texa user-facing UI, navigation, layouts, components, visual hierarchy, responsive desktop behavior, accessibility, copy, or interaction patterns. Apply it to React, CSS, Electron surfaces, screenshots, and product design decisions in the Texa repository.
---

# Texa UI System

Texa is a desktop learning harness, not a chatbot. Its core content area is a document-oriented workspace for learning tasks. The product model lives in 00-product-model.md; the content surface is defined in 03-learning-canvas.md.

Give this skill final authority over Texa product visual language. If a generic frontend skill conflicts with this skill, follow Texa UI System for product structure, density, typography, surfaces, color, and interaction. Preserve repository architecture, backend contracts, learning data, Markdown, KaTeX, streaming, citations, and typed repair workflows.

## Required workflow

1. Audit the real route, component tree, state, and running UI before changing a surface.
2. Identify the primary user task, persistent learning context, and secondary information.
3. Read only the references needed for the task, using the routing table below. For a concrete task, start from 12-task-patterns.md.
4. Prefer structural correction before visual polish.
5. Reuse existing business logic and feature hooks. Add primitives only when they will be reused.
6. Verify desktop Electron behavior at minimum, normal laptop, and wide widths.
7. Inspect screenshots twice: first for hierarchy and flow, then for visual consistency.
8. Run the anti-slop and regression checks in 11-review.md before completion.

## Reference routing

- Product objects, identity, and product voice: [00-product-model.md](references/00-product-model.md)
- Scenes, learning flow, and route responsibilities: [01-learning-flow.md](references/01-learning-flow.md)
- Context regions, responsive behavior, and page contracts: [02-page-layout.md](references/02-page-layout.md)
- Learning Canvas, answer as document, and long-form reading: [03-learning-canvas.md](references/03-learning-canvas.md)
- Reusable components (button, menu, composer, inspector, disclosure): [04-components.md](references/04-components.md)
- Keyboard, focus, motion, and progressive disclosure: [05-interaction.md](references/05-interaction.md)
- Type tokens: [06-typography.md](references/06-typography.md)
- Semantic color tokens: [07-color.md](references/07-color.md)
- Spacing and density tokens: [08-spacing.md](references/08-spacing.md)
- Surface tokens (hierarchy, radius, borders, shadow): [09-surfaces.md](references/09-surfaces.md)
- User-perceivable states: [10-states.md](references/10-states.md)
- Review checklist and mechanical review: [11-review.md](references/11-review.md)
- Common task patterns: [12-task-patterns.md](references/12-task-patterns.md)
- External evidence: [13-reference-harnesses.md](references/13-reference-harnesses.md)

## Cross-cutting invariants

- Keep the main workspace dominant and predictable.
- Keep current scope and session recognizable without repeating them everywhere.
- The answer area is a learning document, not a chat card.
- Sources, concepts, and metadata are progressively disclosed.
- Do not hide typed repair states, repair progress, retry, or logs.
- Use neutral surfaces, one restrained Texa accent, hairline borders, and minimal elevation.
- Use functional, short Chinese copy without marketing language or repeated AI framing.

## Scope guardrail

Stay within presentation, navigation, component system, and interaction design. Do not redesign APIs, retrieval, embeddings, Chroma, session persistence, or databases for a UI task. When the interface truly needs backend work, record `UX_BLOCKED_BY_BACKEND` with the smallest required contract change and continue with safe frontend work. Do not map backend schema, fields, or enums into the product model.
