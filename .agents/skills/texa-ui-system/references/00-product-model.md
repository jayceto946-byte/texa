# Product model

## Purpose

Define Texa's product objects from the user's cognition, and map each object to its UI role. This is a `product object → UI role` mapping, not a `database object → UI field` mapping. Do not carry backend fields, enums, or storage structure into this file.

## Core axiom

Texa is a learning environment, not a chatbot. Learning objects and evidence carry identity; the model does not carry identity and is never the product hero.

## Objects

Each object has three attributes: user understanding, UI responsibility, presentation.

### Learning Scope

- User understanding: the current learning environment.
- UI responsibility: expresses the knowledge scope and context the AI is currently working within.
- Presentation: persistent context bar / sidebar.

Rules:
- Must remain perceivable, but must not be stacked repeatedly.
- Not equivalent to Textbook, Session, or Concept.
- Connects: subject, textbook, chapter, current learning goal.

### Textbook

- User understanding: source of learning material.
- UI responsibility: provides learning scope and authoritative context; owns the evidence and content it contains.
- Presentation: selector / row / inspector.

Rules:
- A learning object that carries identity, not a decorative object.
- Role semantics at user level only (e.g., main vs supplementary material), never backend field constraints.

### Session

- User understanding: a continuous learning record.
- UI responsibility: organizes workspace content; supports resume and review.
- Presentation: sidebar history row; single title at workspace top.

Rules:
- A new session inherits the current scope unless the user explicitly changes it.
- Session history belongs to learning-scene navigation; it is not a separate analytics page.

### Question

- User understanding: a learning problem the user poses (text, formula, or attachment).
- UI responsibility: drives one learning action (retrieval, explanation, practice).
- Presentation: lightweight query header on the Learning Canvas, not a bubble.

Rules:
- Attachments are split from the question body as a pure presentation concern.

### Answer

- User understanding: learning content produced for a question (explanation, derivation, example, summary).
- UI responsibility: carries the learning content itself.
- Presentation: document flow on the Learning Canvas.

Rules:
- Answer is one content type of the Learning Canvas, not a chat message card.

### Source

- User understanding: textbook provenance supporting content.
- UI responsibility: trust infrastructure; makes content traceable.
- Presentation: citation number in body + compact source row + inspector.

Rules:
- Grouped by chapter; never decorative cards.

### Concept

- User understanding: a knowledge node.
- UI responsibility: connects learning, review, and related knowledge.
- Presentation: inline link in body / compact metadata row / inspector.

Rules:
- Not a tag or decoration.
- Presented as navigation only when an inspect or follow action exists.

### Mistake

- User understanding: a problem with a recorded cause.
- UI responsibility: drives review and attribution.
- Presentation: row / list / detail.

Rules:
- Explanation may inject textbook context; generic problems may fall back to plain explanation.

### Exercise

- User understanding: a traceable practice or past-exam problem.
- UI responsibility: supports the practice scenario with traceable sources.
- Presentation: collection list + practice mode.

### ReviewItem

- User understanding: a mistake or concept due for review.
- UI responsibility: drives the review queue.
- Presentation: list row.

Rules:
- Progress is shown only when it can change the next study action.

## Object → UI role matrix

| Object | Default presentation | Carried by | Escalates to card / inspector only when |
|---|---|---|---|
| Learning Scope | persistent context bar / sidebar region | Context sidebar | — |
| Textbook | selector / row | Library scene, scope | inspected in detail |
| Session | history row + workspace title | Context sidebar / workspace | — |
| Question | query header on canvas | Learning Canvas | — |
| Answer | document flow | Learning Canvas | — |
| Source | citation + compact row | Learning Canvas body | inspected |
| Concept | inline link / compact row | Learning Canvas body | inspected |
| Mistake | row / list / detail | Review scene | opened as detail |
| Exercise | collection row / practice | Exercises scene | practice mode |
| ReviewItem | list row | Review scene | — |

## Cross-object rules

- One dominant object per surface.
- Secondary evidence, metadata, and progress detail are progressively disclosed; they do not occupy the primary surface.
- Persistent context is preferred over repeated selectors and confirmation dialogs.
- Prefer predictable paths over artificially low click counts.

## Product voice

- Short, specific, functional Chinese copy.
- Avoid marketing language and repeated AI framing (`AI-powered`, 智能赋能, 探索, 开启旅程, 魔法, 全新体验).
- Avoid reminders that the system uses AI when they add no decision value.
