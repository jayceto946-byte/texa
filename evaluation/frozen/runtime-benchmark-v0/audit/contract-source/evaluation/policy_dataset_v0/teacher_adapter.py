"""Narrow future protocol. No transport, provider, credentials or LLM imports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from backend.services.decision.policy_contracts import PolicyObservationV0
from .serialization import policy_input, invoke_policy


@dataclass(frozen=True)
class NotRun:
    status: str = "disabled/not_run"


class TeacherAdapterV0(Protocol):
    enabled: bool
    test_only: bool

    def __call__(self, observation: PolicyObservationV0) -> object: ...


class DisabledTeacherV0:
    enabled = False
    test_only = False

    def __call__(self, observation: PolicyObservationV0):
        policy_input(observation)
        return NotRun()


def call_teacher(adapter: TeacherAdapterV0, observation: PolicyObservationV0):
    return invoke_policy(adapter, observation)
