# Legacy single-practice partial result

Date: 2026-10-11  
Status: **FIXED — containment only**

`POST /api/exercises/practice` persists the exercise attempt before optionally creating/linking a mistake record or pending candidate. A failure in that secondary step previously escaped as a failed request even though the practice row had already committed; retrying the whole request could record another attempt. The endpoint now catches exceptions only around the optional linkage branch and returns HTTP 200 with the existing successful practice payload plus `completion_status: "partial"`, `practice_saved: true`, `linkage_status: "unconfirmed"`, and a Chinese warning. The warning says the optional record may already have been written, directs the user to inspect the relevant list, and says not to repeat the full practice request. Exception text is omitted from the response.

The primary `record_practice` path, primary learning-event call and response projection remain outside the catch. Their failures still propagate. Healthy responses retain their previous shape. No retry, rollback, delete, schema, or idempotency behavior was added.

## Verification

The new isolated tests use real `ExerciseBank` and `MistakeBook` SQLite files under `tmp_path` and assert the durable practice count:

- Healthy direct linkage returns the prior response shape and creates the mistake.
- A primary practice write failure propagates and leaves `practice_count` at zero.
- Failure before optional linkage storage returns partial success with exactly one saved practice and omits exception details.
- Failure after the mistake and source/attempt linkage committed returns partial success, preserves the linked records, and keeps practice count at one.

Result: **PASS — 4 tests** using `venv310` / Python 3.10. [Pytest output](evidence/legacy-practice-partial-result-pytest.log).

**Still unresolved:** P2 duplicate risk from a lost successful response/retry remains outside this containment change. A broader idempotency contract needs separate design and approval.
