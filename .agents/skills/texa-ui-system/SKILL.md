---
name: texa-ui-system
description: Use this skill whenever designing, implementing, reviewing, or modifying Texa user-facing UI, navigation, layouts, components, visual hierarchy, responsive desktop behavior, accessibility, copy, or interaction patterns. Apply it to React, CSS, Electron surfaces, screenshots, and product design decisions in the Texa repository.
---

# Texa UI System

Treat Texa as a desktop learning harness organized around textbooks, learning context, sessions, questions, answers, sources, concepts, and actionable progress.

Give this skill final authority over Texa product visual language. If a generic frontend skill conflicts with this skill, follow Texa UI System for product structure, density, typography, surfaces, color, and interaction. Preserve repository architecture, backend contracts, learning data, Markdown, KaTeX, streaming, citations, and typed repair workflows.

## Required workflow

1. Audit the real route, component tree, state, and running UI before changing a surface.
2. Identify the primary user task, persistent learning context, and secondary information.
3. Read only the references needed for the task, using the routing table below.
4. Prefer structural correction before visual polish.
5. Reuse existing business logic and feature hooks. Add primitives only when they will be reused.
6. Verify desktop Electron behavior at minimum, normal laptop, and wide widths.
7. Inspect screenshots twice: first for hierarchy and flow, then for visual consistency.
8. Run the anti-slop and regression checks before completion.

## Reference routing

- Product identity and decision order: [design-principles.md](references/design-principles.md)
- Routes, object hierarchy, and page responsibilities: [information-architecture.md](references/information-architecture.md)
- Sidebar, workspace toolbar, sessions, and inspector: [navigation.md](references/navigation.md)
- Type scale and math-rich reading: [typography.md](references/typography.md)
- Spacing, density, width, and resize behavior: [spacing.md](references/spacing.md)
- Semantic color tokens and Texa accent: [color.md](references/color.md)
- Borders, radius, cards, elevation, and panels: [surfaces.md](references/surfaces.md)
- Composer, controls, disclosure, keyboard, and motion: [interaction.md](references/interaction.md)
- Loading, ready, indexing, repair, error, offline, and empty states: [states.md](references/states.md)
- Prohibited AI-generated patterns and review checklist: [anti-ai-slop.md](references/anti-ai-slop.md)
- Abstract lessons from mature productivity harnesses: [reference-harnesses.md](references/reference-harnesses.md)

## Product invariants

- Keep the main workspace dominant and predictable.
- Keep current scope and session recognizable without repeating them everywhere.
- Keep navigation persistent; disclose secondary context progressively.
- Put the answer first. Move evidence, concepts, metadata, and progress detail to compact rows or a contextual inspector.
- Treat sources as trust infrastructure, not decorative cards.
- Show concepts as navigation only when an inspect or follow action exists.
- Show progress only when it can change the next study action.
- Use neutral surfaces, one restrained Texa accent, hairline borders, and minimal elevation.
- Use functional, short Chinese copy. Avoid marketing language and repeated AI framing.
- Do not hide typed ONNX failures, repair actions, repair progress, retry, or logs.

## Scope guardrail

Stay within presentation, navigation, component system, and interaction design. Do not redesign APIs, retrieval, embeddings, Chroma, session persistence, or databases for a UI task. When the interface truly needs backend work, record `UX_BLOCKED_BY_BACKEND` with the smallest required contract change and continue with safe frontend work.

## Completion checks

- Confirm QA streaming, Markdown, LaTeX, citations, source expansion, concepts, history, book context, progress, settings, and repair states still work.
- Confirm focus visibility, keyboard navigation, contrast, button semantics, and non-color status cues.
- Confirm there is no card soup, pill-everything, decorative gradient, blur, shadow, badge, illustration, animation, or loading.
- Confirm the result reads as Texa, a mature learning tool, even without the logo.
- Confirm the result does not read as a Codex reskin or generic AI SaaS template.
