"""Measured native tool capability, bound to exact connection and credentials."""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
from llm.types import Capability, ResolvedModelRole


def _path() -> Path:
    from config import PROGRESS_PATH
    return Path(PROGRESS_PATH) / 'tool_capabilities.json'


def _identity(resolved: ResolvedModelRole) -> str:
    # Only a digest is stored; changing endpoint, model, options or key invalidates it.
    value = [resolved.role.value, resolved.provider.provider_id, resolved.provider.transport,
             resolved.model, resolved.endpoint, resolved.api_key, dict(resolved.options)]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def has_verified_tool_capability(resolved: ResolvedModelRole) -> bool:
    from llm.factory import transport_capabilities
    if Capability.TOOL_CALLING not in transport_capabilities(resolved.provider.transport):
        return False
    try:
        receipt = json.loads(_path().read_text()).get(_identity(resolved), {})
        age = time.time() - receipt['verified_at']
        return receipt.get('schema') == 'texa.tool-capability/v1' and 0 <= age < 30 * 86400
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def verify_tool_capability(resolved: ResolvedModelRole, *, client=None) -> bool:
    """Explicit paid probe; no domain tool or user data is sent."""
    from llm.factory import build_openai_client
    if resolved.provider.transport != 'openai_compatible':
        return False
    client = client or build_openai_client(resolved, timeout=30, max_retries=0)
    tools = [{'type': 'function', 'function': {'name': 'texa_capability_probe',
        'description': 'Echo the supplied value to verify tool calling.',
        'parameters': {'type': 'object', 'properties': {'value': {'type': 'string'}},
                       'required': ['value'], 'additionalProperties': False}}}]
    messages = [{'role': 'user', 'content': 'Call texa_capability_probe exactly once with value texa-probe. Do not answer directly.'}]
    response = client.chat.completions.create(model=resolved.model, messages=messages,
        tools=tools, tool_choice='auto', max_tokens=1024,
        extra_body=dict(resolved.options.get('extra_body') or {}))
    calls = response.choices[0].message.tool_calls or []
    if len(calls) != 1 or calls[0].function.name != 'texa_capability_probe':
        return False
    if json.loads(calls[0].function.arguments) != {'value': 'texa-probe'}:
        return False
    path = _path()
    try:
        records = json.loads(path.read_text())
    except (OSError, ValueError):
        records = {}
    if not isinstance(records, dict):
        records = {}
    records[_identity(resolved)] = {'schema': 'texa.tool-capability/v1', 'verified_at': time.time()}
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace atomically so interrupted verification cannot grant partial capability.
    import tempfile
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.tool-capabilities-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(records, stream)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True
