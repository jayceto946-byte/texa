---
name: texa-ui-system
description: Use when designing, implementing, reviewing, or modifying Texa user-facing UI, navigation, layouts, components, visual hierarchy, responsive desktop behavior, accessibility, copy, or interaction patterns.
---

# Texa UI System

Texa is a desktop learning workspace. Keep learning content, evidence, and actionable state clear. Preserve the engineering and data boundaries in `AGENTS.md`.

## Core principles

1. Put learning content, sources, and necessary state first. Decoration must not compete with them.
2. Express hierarchy through position, alignment, spacing, weight, and useful boundaries.
3. Use the same control for the same meaning. Differences should serve a task or native platform capability.
4. Use two content archetypes: Reading Canvas for questions, answers, formulas and evidence; management workspace for collections, records, forms and review actions. Keep reading comfortable and controls compact.
5. Show real states clearly, with text or shape as well as color. Keep recovery actions discoverable.
6. Judge the rendered UI in relevant states and window sizes; revise rules when evidence warrants it.

## Sources of truth

- The populated [Learning reference](../../../artifacts/study-desk/learning-final-type.png) and [Textbook reference](../../../artifacts/study-desk/textbooks-final-type.png) are the approved visual ground truth. Preserve their composition during extraction and page migration.
- `frontend/src/layouts/ApprovedWorkspace.css` holds shared visual roles. `frontend/src/layouts/StudyDesk.css` contains the original two-page implementation; use its effective, last-applied rules when checking parity. `frontend/src/theme.ts` retains theme identities and stored user preference.
- Existing component APIs and interaction logic remain authoritative for behavior. Legacy page styling cannot override the approved visual reference.
- Read [product objects](references/00-product-model.md), [learning canvas](references/03-learning-canvas.md), or [states](references/10-states.md) when relevant.

## Acceptance checklist

1. Inspect a populated route and its interactions before editing. For Learning and Textbook, compare rendered output with the approved screenshots before propagating shared roles.
2. Keep the Reading Canvas and management workspace hierarchy consistent. Distinguish titles, content, controls and metadata at full and thumbnail size. Keep learning content, provenance and the next action clear.
3. Verify long Chinese text, equations, citations, long names, mixed statuses, loading, empty, error, disabled, selected, focus, expanded detail and recovery states.
4. Check 1280×820, 1024×768 and 760×820 desktop sizes. No clipped controls, horizontal register overflow or composer-covered reading content.
5. Preserve keyboard behavior, state labels and theme preference. Shared UI is the same on Windows and macOS apart from native window controls and drag behavior.
6. Run relevant tests, lint and build. Record actual visual checks separately from source inspection and name platforms that were not tested.

Brand and font assets live in `frontend/src/assets/`, `frontend/public/brand/`, and `desktop/assets/`; license notes live in `THIRD_PARTY_NOTICES/fonts/`.
