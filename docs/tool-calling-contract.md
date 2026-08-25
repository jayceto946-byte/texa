# Texa Tool Calling Contract

## Scope

Texa tools are bounded capabilities inside the learning harness. They are not
general code execution and do not replace the Resolver, production retrieval,
EvidencePack or answer generator.

The main chat owns one answer path:

```text
Resolver -> bounded tool orchestration -> planner/retrieval -> EvidencePack
         -> generator -> Answer / Solution / Evidence / Execution Trace
```

The compatibility `/api/agent/*` endpoints use the same registry and
orchestration service, but they are not a second production answer pipeline.

## Tool contract

Every registered tool publishes:

- stable name and version;
- input and result schemas;
- capability labels;
- read/write classification and risk level;
- timeout budget;
- provenance;
- a handler returning `ToolResult`.

`ToolResult` separates:

- `data`: typed returned values;
- `evidence`: source metadata supporting retrieved claims;
- `verification`: deterministic postcondition status;
- `warnings`: limitations that must survive answer synthesis;
- `pending_action`: a proposal that has not modified user state.

Execution success means only that the handler returned successfully. It does
not establish that the selected tool was appropriate or that the final answer
is correct.

## Runtime policy

- Main-chat tool selection is server-side. The frontend renders SSE events and
  never chooses the answer pipeline.
- A request exposes at most six relevant tools and uses a bounded total time.
- Textbook retrieval uses the production retrieval node, evidence support gate
  and final EvidencePack. A second simplified vector-search path is prohibited.
- Deterministic mathematics uses a restricted AST grammar. Arbitrary Python,
  shell execution, imports, attribute access and model-produced code are
  prohibited.
- Symbolic results that support verification automatically invoke the verifier.
- Read-only tools may run automatically. Mutations remain proposals until the
  user explicitly confirms them through the owning workflow.
- Tool failure degrades to the existing answer path and remains visible in the
  execution trace. It must not erase already generated answer content.

## Prompt boundary

Tool Context Pack is bounded quoted data. The generator may use:

- EvidencePack for textbook claims;
- verified mathematical results for the returned calculation;
- local learning-state tools for the returned user state;
- exercise tools for the returned exercise records.

The generator must preserve warnings, failed verification and pending status.
It may not infer that an unreturned field was checked or that a proposal was
executed.

## Evaluation gates

Offline routing evaluation reports these dimensions separately:

- tool-route exact match;
- no-tool overcall rate;
- operation/argument match where applicable;
- tool execution success;
- deterministic verification pass rate;
- results by task category.

The offline suite does not claim model answer accuracy. Online answer quality,
EvidencePack coverage, citation support, latency and token cost remain separate
release gates.

Initial offline thresholds:

- route exact match >= 0.90;
- no-tool precision >= 0.95;
- supported math execution success = 1.00;
- supported math verification pass = 1.00.

