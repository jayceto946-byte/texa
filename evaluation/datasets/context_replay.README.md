# Context replay dataset

`context_replay.py` writes redacted candidates to `data/eval/`; candidates are
not release goldens. Review a candidate locally, add explicit `expected`
contracts, change `status` to `approved`, and place only approved/non-sensitive
cases in a versioned JSONL dataset.

Required fields: `schema_version`, `id`, `status`, `history`, `query`,
`book_name`, and `expected`. Production retrieval expectations may include
`resolved_query`, `required_evidence_points`, `forbidden_evidence_points`,
`retrieval_action`, `support_status`, `context_turn_ids`, and
`artifact_targets`. Online answer expectations may include
`required_answer_points`, `required_constraints`, `forbidden_answer_terms`,
and `require_citations`.
