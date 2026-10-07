"""Release contract: changing these shapes requires an explicit new baseline."""
import json
import sqlite3
from dataclasses import fields
from pathlib import Path
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from backend.services.execution_events import EXECUTION_EVENT_V1_CONTRACT, EXECUTION_EVENT_V2_SCHEMA, _REQUIRED_EVENT_FIELDS, _OPTIONAL_EVENT_FIELDS
from backend.tools.registry import ToolResult, ToolRegistry
from memory.learning_events import LearningEventStore


def test_runtime_v0_release_contract(tmp_path):
    baseline = json.loads((Path(__file__).parents[1] / 'docs/contracts/agent-runtime-v0.json').read_text())
    store = RuntimeStore(tmp_path / 'runtime.db')
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == baseline['sqlite_schema']
        for name, table in [('AgentRun', 'agent_runs'), ('ToolCall', 'tool_calls')]:
            assert [row[1] for row in conn.execute('PRAGMA table_info(' + table + ')')] == baseline[name]['columns']
    assert [item.name for item in fields(ToolResult)] == baseline['ToolResult']['fields']
    assert set(ToolResult(True).to_dict()) == set(baseline['ToolResult']['fields'])
    actual = {key: sorted(value) if isinstance(value, (set, frozenset, tuple)) else value
              for key, value in EXECUTION_EVENT_V1_CONTRACT.items()}
    assert actual == baseline['ExecutionEvent']['v1']
    assert EXECUTION_EVENT_V2_SCHEMA == baseline['ExecutionEvent']['v2_schema']
    assert sorted(_REQUIRED_EVENT_FIELDS) == baseline['ExecutionEvent']['required_fields']
    assert sorted(_OPTIONAL_EVENT_FIELDS) == baseline['ExecutionEvent']['optional_fields']
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, LearningEventStore(tmp_path / 'events.db'))
    metadata = registry.runtime_tool('get_recent_progress').runtime_metadata()
    assert sorted(metadata) == baseline['ToolRegistry']['metadata_fields']
    assert metadata['input_schema'] == baseline['ToolRegistry']['recent_progress_input']
    assert metadata['output_schema'] == baseline['ToolRegistry']['recent_progress_output']
