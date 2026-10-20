# UI review

Use the acceptance checklist in the parent `SKILL.md` as the single review sequence. Product state and recovery details remain in `10-states.md`.

During that sequence, keep a short evidence sheet for the changed interaction:

| Applicable case | Record / check |
|---|---|
| An existing component changes | Its consumers and effective style source; reuse the same interaction contract even when placement differs. Check an adjacent consumer before extracting a new abstraction. |
| Controls change | Normal, enabled hover, keyboard focus, pressed/selected, disabled, busy and error where present. Check fixed geometry and that a disabled control does not look actionable. |
| A menu or selection group changes | Open, movement, confirmation, dismissal and focus return/exit; screen roles must match behavior. Use the existing Dialog and SelectionControls capabilities before importing replacements. |
| A transition changes | Name its purpose (continuity, state feedback or placement), reuse current motion roles and check reduced-motion. Static feedback is sufficient when it already explains the change. Do not animate math text merely to demonstrate streaming. |
| Input or reading changes | Long Chinese, equations, references, a bounded input and reachable submit/stop; composition events and newline/submit are separate checks. Evaluate available container width, including inspectors. |
| A reference implementation informs a rule | Pin the source revision and distinguish code, author explanation and your inference. A demo and a comment are not proof of accessibility or production state correctness. |
| Completion is reported | Before/after screenshots of the same state, actual tests, inspected sizes and explicit untested platforms. Wait for the real content rather than capturing a skeleton; do not equate compilation with visual acceptance. |

Basis: [fixed-source research and Electron trial](../../../../docs/design/claude-ui-source-study-2026-10-19.md). The sheet supplements the parent review sequence; it does not create a parallel token or component system.
