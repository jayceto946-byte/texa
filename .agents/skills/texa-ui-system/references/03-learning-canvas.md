# Learning Canvas

## Core definition

Texa's core content area is not a chat message stream. It is a document-oriented workspace for learning tasks. It supports Question, Explanation, Summary, Review, Source, and Learning document. Answer is one content type of the Learning Canvas.

Explicit non-goals:
- Not a chatbot.
- Not a stream of chat bubbles or assistant message cards.
- Not an analytics or dashboard surface.

## Content axis

- Question, Answer content, and the Composer share the same content axis.
- Keep the reading column width stable (about 72ch for Chinese and mixed math text); allow horizontal overflow for tables and display formulas.
- Body line height 1.6–1.72 for explanations.

## Question presentation

- Question renders as a lightweight query header on the canvas.
- No block background, border, shadow, or emphasis line.
- Attachments are split from the question body as a pure presentation row.

## Answer as document flow

- Answer renders as an open document flow on the workspace surface.
- Hierarchy is expressed with weight and spacing before increasing size.
- Markdown headings are restrained and proportionate to the answer.
- Strong weight (600) is reserved for core conclusions, concepts, and key causal/contrast statements.
- Content supports selection and copying.
- Inline formulas align with the Chinese body baseline.

## Content types

Answer is one content type; the canvas also hosts:

- Explanation / derivation: full steps are allowed to be expanded.
- Summary: concise, conclusion-led.
- Review: connects to ReviewItem objects and next review action.
- Learning document / study note: long-form, source-anchored.
- Exercise solution: traceable to sources.

## Progressive disclosure inside the canvas

- Source: citation number in body + compact source row inside the canvas; detail expands into the inspector.
- Concept: inline link or compact metadata row; detail expands into the inspector.
- Metadata: compact row or inspector only; not repeated on the primary surface.
- Utility content (reports, exercise cards, chapter highlights, agent cards): secondary content that must not dominate the primary surface.

## Consistency

- Question, Answer, and Composer align on one content axis.
- The canvas never renders as a chat bubble, assistant card, or message list.
- When the surface narrows, the canvas and Composer shrink together without horizontal overflow or cropping.
