"""Goal writes and evidence checks; suggestions never execute a run."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.services.goals.store import GoalConflict, GoalStore
from memory.learning_events import LearningEvent, LearningEventStore


class GoalService:
    def __init__(self, store: GoalStore, events: LearningEventStore | None = None):
        self.store = store
        self.events = events

    def create(self, **kwargs) -> dict:
        return self.store.create(**kwargs)

    def update(self, goal_id: str, *, expected_revision: int, changes: dict) -> dict:
        if set(changes) - {"title", "objective", "scope", "success_criteria", "target_date", "timezone"}:
            raise ValueError("manual update cannot change lifecycle or measured progress")
        goal = self.store.get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        changes = {key: value for key, value in changes.items() if goal.get(key) != value}
        if "success_criteria" in changes or "objective" in changes or "scope" in changes:
            criteria = changes.get("success_criteria", goal["success_criteria"])
            changes = {**changes, "progress": {"criterion_results": [], "evidence_refs": [],
                       "measured_at": None, "unknowns": [item.get("id") for item in criteria]},
                       "next_action": None}
        updated = self.store.update(goal_id, expected_revision=expected_revision, changes=changes)
        if set(changes) & {"objective", "scope", "success_criteria"}:
            self._interrupt_runs(goal_id)
        if updated["status"] == "active":
            self._project(updated, "goal_created")
        return updated

    def activate(self, goal_id: str, *, expected_revision: int) -> dict:
        goal = self.store.get(goal_id)
        if not goal or goal["status"] not in {"draft", "paused"}:
            raise GoalConflict("goal cannot be activated")
        updated = self.store.update(goal_id, expected_revision=expected_revision,
                                    changes={"status": "active"})
        self._project(updated, "goal_created")
        return updated

    def pause(self, goal_id: str, *, expected_revision: int) -> dict:
        goal = self.store.get(goal_id)
        if not goal or goal["status"] != "active":
            raise GoalConflict("goal is not active")
        updated = self.store.update(goal_id, expected_revision=expected_revision,
                                    changes={"status": "paused"})
        self._interrupt_runs(goal_id)
        self._project(updated, "goal_paused")
        return updated

    def measure(self, goal_id: str, *, expected_revision: int,
                evidence_by_criterion: dict[str, list[str]],
                user_confirms_completion: bool = False) -> dict:
        goal = self.store.get(goal_id)
        if not goal or goal["revision"] != expected_revision:
            raise GoalConflict("goal revision changed")
        results, evidence_refs, unknowns = [], [], []
        for criterion in goal["success_criteria"]:
            criterion_id = str(criterion.get("id") or "")
            refs = [str(ref) for ref in evidence_by_criterion.get(criterion_id, []) if str(ref)][:20]
            evidence_refs.extend(refs)
            if not refs:
                unknowns.append(criterion_id)
            results.append({"criterion_id": criterion_id,
                            "status": "evidence_present_unverified" if refs else "unknown",
                            "evidence_refs": refs})
        progress = {"criterion_results": results, "evidence_refs": list(dict.fromkeys(evidence_refs))[:100],
                    "measured_at": datetime.now(timezone.utc).isoformat(),
                    "unknowns": unknowns}
        changes = {"progress": progress}
        if user_confirms_completion:
            changes["status"] = "completed"
        updated = self.store.update(goal_id, expected_revision=expected_revision, changes=changes)
        if updated["status"] == "completed":
            self._project(updated, "goal_completed")
        return updated

    def _interrupt_runs(self, goal_id):
        from backend.services.agent_runtime.locator import runtime_store
        from backend.services.agent_runtime.contracts import RuntimeConflict
        store = runtime_store()
        if store is None:
            return
        for link in self.store.links(goal_id):
            snapshot = store.task_snapshot(link["task_id"])
            if snapshot and snapshot["task"]["status"] == "waiting_for_confirmation":
                for approval in snapshot.get("approvals", []):
                    if approval["status"] == "pending":
                        try:
                            store.reject_approval(approval["call_id"], actor_id="goal_changed")
                        except RuntimeConflict:
                            pass
            if snapshot and snapshot["run"]["status"] == "running":
                try:
                    store.close(snapshot["run"]["id"], snapshot["run"]["owner_token"], outcome="paused", error_code="goal_changed")
                except RuntimeConflict:
                    pass

    def evidence_candidates(self, goal_id: str) -> list[dict]:
        goal = self.store.get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        if self.events is None:
            return []
        scope = goal.get("scope") or {}
        events = self.events.list_recent(learner_id=goal["learner_id"],
            book_name=str(scope.get("book_name") or ""),
            subject=str(scope.get("subject") or ""), limit=100)
        labels = {"exercise_practiced": "习题作答", "chat_qa": "学习问答",
                  "chat_teach": "教材讲解", "chat_summarize": "章节总结",
                  "mistake_reviewed": "错题复习"}
        return [{"id": event.id, "label": labels[event.event_type],
                 "timestamp": event.timestamp, "book_name": event.book_name}
                for event in events if event.event_type in labels][:50]

    def get_next_action(self, goal_id: str) -> dict:
        goal = self.store.get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        if goal["status"] != "active":
            return {"capability_id": None, "reason_codes": ["goal_not_active"],
                    "approval_required": False}
        unknowns = goal["progress"].get("unknowns") or []
        if unknowns:
            return {"capability_id": "learning.inspect", "input_refs": [],
                    "prerequisites": unknowns[:5], "approval_required": False,
                    "reason_codes": ["measurement_unknown"]}
        return {"capability_id": None, "reason_codes": ["user_review_needed"],
                "approval_required": False}

    def _project(self, goal: dict, event_type: str) -> None:
        if self.events is None:
            return
        scope = goal.get("scope") or {}
        event = LearningEvent(id=f"evt_{goal['id']}_{goal['revision']}",
            timestamp=goal["updated_at"],
            event_type=event_type, learner_id=goal["learner_id"],
            book_name=str(scope.get("book_name") or ""),
            book_id=str((scope.get("book_ids") or [""])[0]),
            chapter_id=str((scope.get("chapter_ids") or [""])[0]),
            subject=str(scope.get("subject") or ""), source_type="goal", source_id=goal["id"],
            payload={"goal_id": goal["id"], "target_name": goal["title"],
                     "status": goal["status"], "goal_revision": goal["revision"],
                     **{key: scope[key] for key in ("target_type", "target_id", "chapter_name", "unit_name") if key in scope}})
        self.events.append(event)

    def reconcile_projections(self, goal_id: str) -> int:
        """Replay stable event IDs after a goal commit/projector interruption."""
        revisions = self.store.revisions(goal_id)
        if not revisions:
            raise KeyError(goal_id)
        count = 0
        previous = "draft"
        previous_goal = None
        event_types = {"active": "goal_created", "paused": "goal_paused",
                       "completed": "goal_completed"}
        for goal in revisions:
            status = goal["status"]
            changed = previous_goal is not None and any(goal[key] != previous_goal[key] for key in ("title", "objective", "scope", "success_criteria"))
            if (status != previous or (status == "active" and changed)) and status in event_types:
                self._project(goal, event_types[status])
                count += 1
            previous = status
            previous_goal = goal
        return count
