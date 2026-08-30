"""Deterministic release checks for the LearningTask lifecycle.

This suite deliberately avoids model calls.  It verifies that production task
primitives stop, wait, resume, degrade and finish with durable checkpoints.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from backend.services.answer_verification import verify_answer
from backend.services.learning_task import (
    LearningTaskStore,
    blocking_required_inputs,
    interrupt_learning_task,
    mark_required_inputs,
    resume_learning_task,
)


def _case(name: str, passed: bool, actual: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual}


def evaluate_learning_task_lifecycle() -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="texa-lifecycle-eval-") as root:
        store = LearningTaskStore(Path(root))

        waiting = store.create(
            task_type="visual_qa",
            goal="根据附表计算温度",
            status="waiting_for_input",
            required_inputs=[{
                "type": "reference_table", "name": "分度表", "reason": "反查温度",
                "affects": ["final_numeric_answer"], "blocking": True,
            }],
        )
        waiting_task_id = waiting.id
        cases = [_case(
            "blocking_input_stops_before_answer",
            waiting.status == "waiting_for_input" and bool(blocking_required_inputs(waiting.required_inputs)),
            waiting.status,
        )]

        mark_required_inputs(waiting, "provided")
        waiting = store.checkpoint(waiting, "input_provided", status="running")
        cases.append(_case(
            "provided_input_resumes_same_task",
            waiting.id == waiting_task_id and waiting.status == "running" and not blocking_required_inputs(waiting.required_inputs),
            {"same_task": waiting.id == waiting_task_id, "status": waiting.status},
        ))

        interrupted = store.create(task_type="qa", goal="证明并计算")
        interrupted = interrupt_learning_task(
            store, interrupted, stage="generate", partial_output="已完成公式推导",
        )
        resumed = resume_learning_task(store, interrupted, run_id="run-evaluation")
        cases.append(_case(
            "interrupted_task_keeps_checkpoint_and_resumes",
            resumed.status == "running"
            and resumed.artifacts.get("partial_output") == "已完成公式推导"
            and [item.get("stage") for item in resumed.checkpoints[-2:]] == ["interrupted", "resumed"],
            {"status": resumed.status, "stages": [item.get("stage") for item in resumed.checkpoints[-2:]]},
        ))

        method_only = verify_answer(
            "由关系式可列出计算步骤；由于缺少附表，本轮不提交精确数值。",
            required_outputs=[{"id": "final_numeric_answer", "kind": "numeric", "required": True}],
            answer_policy="method_only",
        )
        cases.append(_case(
            "waived_input_degrades_instead_of_claiming_exactness",
            method_only.get("status") == "degraded",
            method_only.get("status"),
        ))

        failed = verify_answer(
            "只有解释，没有结果。",
            required_outputs=[{"id": "part_2", "kind": "question_part", "anchors": ["温度补偿"], "required": True}],
        )
        cases.append(_case(
            "failed_contract_is_not_complete",
            failed.get("status") == "failed" and failed.get("passed") is False,
            failed.get("status"),
        ))
        return cases
