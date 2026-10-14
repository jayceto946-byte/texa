# RuntimeEvent V1

## Existing runtime audit

- `backend/conversation_memory.py` stores the conversation event log and recent JSON projection. Its messages are content records, not an execution audit.
- `backend/services/execution_events.py` defines the SSE execution protocol. LearningTask stores only selected milestones (and caps the artifact window at 40); the bounded agent runtime stores its own run milestones in `agent_runtime.db`.
- `backend/rag_trace.py` and `backend/services/decision/trace.py` hold separate diagnostic and routing traces. They do not share turn identity or a complete State → Decision → Execution → Result → Outcome chain.
- Python `logging` is diagnostic output. Its unstructured text is not a stable replay or training contract.

## Contract and boundary

`backend/services/runtime_events.py` is the single V1 schema and writer. Every event has `schema`, `event_id`, `parent_event_id`, UTC `timestamp`, `session_id`, `turn_id`, `request_id`, `task_id`, `run_id`, `app_version`, `runtime_version`, `router_version`, `type`, and an allowlisted `payload`. Scheduled or goal runs without a conversation use an explicit `origin:<kind>:<id>` session identity and an empty turn ID; no conversation turn is invented.

Types are `user_input`, `context`, `active_goal`, `state`, `decision`, `tool_call`, `retrieval`, `model_call`, `state_transition`, `execution_result`, `error`, `retry`, `user_outcome`, and `feedback`. The writer accepts only bounded scalar metadata and validated source/content/chunk references. Input text is represented by SHA-256 plus character count. Prompts, model reasoning, tool arguments/results, full answers, credentials, account details, file paths, and full textbook content are outside the payload contract. Source refs with path separators are discarded.

The existing SSE protocol remains the UI transport. Its events are projected through one adapter into RuntimeEvent. The main chat adds input, goal, route, model, retrieval reference, and outcome points; the bounded runtime uses the same adapter for lifecycle milestones and adds its selected route. Feedback links to the persisted assistant message. The event database is independent of conversation, task, and vector data.

SQLite `runtime_events.db` uses WAL and indexes `(session_id, turn_id, timestamp, event_id)` plus request ID. A bounded in-memory queue writes batches of up to 128 on a background thread. The oldest completed turn is rotated when the store exceeds 100,000 rows; an unfinished turn is retained. A queue overflow or repeated write failure is reported to diagnostic logging; it never blocks the answer path. The replay endpoint `GET /api/chat/runtime-events?session_id=...&turn_id=...` flushes queued writes, returns ordered events, parent links, and the reconstructed metadata state. A session query omits `turn_id`. A long replay uses `next_cursor` as the next request's `after_event_id`; each page is capped at 5,000 events by default. The state field reflects the current page, so a full session state is obtained by applying all pages in order. A retained history may be incomplete after rotation; `parent_present` exposes missing parents. Replay is deterministic for the saved metadata and references; reproducing model output requires the original model, prompt, and corpus versions, which V1 intentionally does not store.

Diagnostic traces serve incident inspection. New RAG diagnostic writes redact recognizable credentials, email addresses, and absolute local paths; preexisting diagnostic rows are not rewritten. RuntimeEvent is the bounded operational audit. A future Training Trace must be curated from RuntimeEvent plus reviewed outcomes with separate retention, consent, and quality gates; these events are not training labels by themselves.
