"""Shared HTTP/SSE mapping for conversation admission failures."""
import json

from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

from backend.services.conversation_management import ConversationManagementError, assert_conversation_writable
from backend.services.goals.service import GOAL_CONTROL_LOCK


def management_error_response(exc):
    return JSONResponse(status_code=exc.status, content={
        'success': False, 'code': exc.code, 'message': str(exc), **exc.details})


def require_writable_conversation(conversation_id):
    with GOAL_CONTROL_LOCK:
        assert_conversation_writable(conversation_id)


class ConversationManagementRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def mapped(request):
            try:
                return await handler(request)
            except ConversationManagementError as exc:
                return management_error_response(exc)
        return mapped


def guarded_conversation_events(events, *, request_id):
    # A concurrent management change can win after the initial HTTP preflight.
    try:
        yield from events
    except ConversationManagementError as exc:
        from backend.services.execution_events import ExecutionEventEmitter, execution_sse_payload
        emitter = ExecutionEventEmitter(request_id=request_id, audit=False)
        event = emitter.emit('error', phase='context', status='failed', summary=str(exc),
            operation_id='conversation-admission', label='会话暂时无法继续', kind='system',
            payload={'error_code': exc.code})
        yield 'data: ' + json.dumps(execution_sse_payload(event), ensure_ascii=False) + '\n\n'
