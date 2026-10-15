# Focus storage contract — authorized implementation, isolated verification first

Additive tables in existing goals.db: focus_tasks(id,goal_id,title,content,duration_seconds,status,revision); focus_state(single local learner row,revision,current_task_id,status,started_at,elapsed_seconds); focus_receipts(operation_id,payload_hash,response_json). No new DB or Runtime state authority.

Migrate goal schema1→2 in one transaction; sqlite backup first for any existing DB, no existing Goal/run/link updates. GoalStore accepts v2. V1 binary rejects v2 rather than silently opening incompatible data. Rollback retains v2 DB+receipts, task export and uses pre-migration backup only with explicit acceptance of any later changes; production DB remains untouched during development. Full restore simulation on disposable DB required before deployment.

One active focus row; commands have expected_revision plus stable operation_id. Receipt lookup before CAS; payload mismatch rejected. Start/switch pauses current (elapsed accumulated on its task) and selects target; no LLM invocation. Pause time frozen; resume time starts anew. Complete only explicit user action, no Goal/SM2/Runtime writes. Deadline computed at read, elapsed capped duration; expiry represented by view, never auto-completes. Server timestamps/elapsed authority, client tick display only.

Bounded tasks100 across local learner, goal ownership checked; create content/title/duration validated, no arbitrary payload, goal material scope inherited. Reading/migrating opens storage only when focus endpoint is used. Foreground GET merges display; no automatic POST retries. Failed command retains operation for explicit receipt reconciliation; no localStorage second authority. No offline automatic state mutation or paid model start.
