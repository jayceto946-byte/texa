"""Selection at the existing pre-SQL clarification checkpoint only."""
from backend.services.decision.policy import select_decision, project_outcome
from backend.services.decision.policy_projection import project_observation
from backend.tools.registry import ToolContext, ToolRegistry


def input_gate_observation(task, request_id):
    return project_observation(request=task.artifacts.get("request_question", task.goal),
        resolved_query=task.artifacts.get("resolved_query", task.goal),
        registry=ToolRegistry(), context=ToolContext(), missing_inputs=task.required_inputs, gate=True,
        identity={"request_id": request_id, "task_id": task.id, "position": "pre_sql_clarification_gate",
                  "task_status": task.status})


def input_gate_trace(task, request_id):
    frozen = input_gate_observation(task, request_id)
    records = []
    binding, attempt, _ = select_decision(frozen, current=lambda: frozen, record=records.append)
    if binding["kind"] != "request_input":
        raise ValueError("input gate cannot execute another action")
    return {**attempt.metadata(), "policy_contract_version": frozen.envelope.policy_contract_version,
            "outcome": project_outcome(attempt, task_status="waiting_for_input", execution="succeeded").model_dump()}
