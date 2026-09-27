from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from backend.services.agent_runtime.contracts import FixedAction, RuntimeDenied
from backend.services.agent_runtime.extensions import TriggerCommand, TriggerIngress, register_fake_mcp_read_tool
from backend.services.agent_runtime.runner import FixedRunner
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.execution_events import execution_sse_payload, validate_execution_event_sequence
from backend.tools.registry import ToolRegistry


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str


class FakeMCP:
    source_id = "fake-library"
    source_version = "1"
    def __init__(self):
        self.calls = 0
    def execute(self, tool_id, args):
        self.calls += 1
        return {"value": args["query"]}


def test_no_conversation_trigger_and_mcp_read_share_runtime(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    ingress = TriggerIngress(store)
    command = TriggerCommand("trigger-1", "Inspect", "owner", budget_calls=1)
    first = ingress.submit_fake_schedule(command)
    assert ingress.submit_fake_schedule(command)["run"]["id"] == first["run"]["id"]
    run_id = first["run"]["id"]
    assert first["run"]["conversation_id"] == ""
    mcp = FakeMCP()
    registry = ToolRegistry()
    register_fake_mcp_read_tool(registry, adapter=mcp, tool_id="mcp_lookup",
                                input_model=Input, output_model=Output)
    blocked = FixedRunner(store, registry, allowlist=frozenset({"mcp_lookup"}))
    with pytest.raises(RuntimeDenied):
        blocked.execute(run_id, "owner", FixedAction("call", tool_id="mcp_lookup",
                        args={"query": "x"}, operation_key="op"))
    assert mcp.calls == 0
    allowed = FixedRunner(store, registry, allowlist=frozenset({"mcp_lookup"}),
                          allowed_sources=frozenset({"mcp"}))
    allowed.execute(run_id, "owner", FixedAction("call", tool_id="mcp_lookup",
                    args={"query": "x"}, operation_key="op"))
    assert mcp.calls == 1
    allowed.execute(run_id, "owner", FixedAction("finish", answer="Done"))
    events = store.events(run_id)
    assert all(item["schema"] == "texa.execution/v2" for item in events)
    assert all(item["origin"] == {"kind": "schedule", "id": "trigger-1"} for item in events)
    assert execution_sse_payload(events[-1])["execution_event"]["type"] == "final"
    validate_execution_event_sequence(events)
    assert store.pending_outbox() == []


def test_unknown_external_schema_and_permission_rejected(tmp_path):
    registry = ToolRegistry()
    mcp = FakeMCP()
    with pytest.raises(RuntimeDenied):
        register_fake_mcp_read_tool(registry, adapter=mcp, tool_id="lookup",
                                    input_model=Input, output_model=Output)
    assert registry.list_tools() == []


@pytest.mark.parametrize("failure", ["unavailable", "permission", "version_changed"])
def test_external_source_fault_isolated_and_never_succeeded(tmp_path, failure):
    store = RuntimeStore(tmp_path / "runtime.db")
    initial = TriggerIngress(store).submit_fake_schedule(TriggerCommand("trigger", "Inspect", "owner", 1))
    adapter = FakeMCP()
    registry = ToolRegistry()
    register_fake_mcp_read_tool(registry, adapter=adapter, tool_id="mcp_lookup", input_model=Input, output_model=Output)
    if failure == "unavailable":
        adapter.is_available = lambda: False
    elif failure == "version_changed":
        adapter.source_version = "2"
    else:
        adapter.execute = lambda *args: (_ for _ in ()).throw(PermissionError("denied"))
    result = FixedRunner(store, registry, allowlist=frozenset({"mcp_lookup"}), allowed_sources=frozenset({"mcp"})).execute(
        initial["run"]["id"], "owner", FixedAction("call", tool_id="mcp_lookup", args={"query": "x"}, operation_key="op"))
    assert result["tool_calls"][0]["status"] == "failed"
    assert result["task"]["status"] == "running"
    assert adapter.calls == 0


def test_trigger_changed_command_cannot_reuse_id(tmp_path):
    from backend.services.agent_runtime.contracts import RuntimeConflict
    store = RuntimeStore(tmp_path / "runtime.db")
    ingress = TriggerIngress(store)
    ingress.submit_fake_schedule(TriggerCommand("trigger", "First", "owner"))
    with pytest.raises(RuntimeConflict, match="changed command"):
        ingress.submit_fake_schedule(TriggerCommand("trigger", "Different", "owner"))
