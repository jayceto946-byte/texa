"""Loopback-only production API fixture. Environment/data are isolated by the launcher."""
import io
import json
import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import uvicorn
from PIL import Image

from backend import conversation_memory as cm
from backend.api import mistakes
from backend.main import app
from backend.services.multimodal_bridge import VisualProblemIR
from llm.deepseek_chat import DeepSeekChatOpenAI
from tests.test_mistakes_api import _configure_visual_stream

root = Path(os.environ["DATA_DIR"])
patch = pytest.MonkeyPatch()
patch.setattr(cm, "CONV_DIR", root / "conversations")
stream = mistakes._iter_visual_solution_chunks
_, tasks = _configure_visual_stream(patch, root, visual_ir=VisualProblemIR(problem_text="所选题目"))
patch.setattr(mistakes, "_image_store", replace(mistakes._image_store, allowed_extensions=frozenset({".png", ".jpg", ".jpeg"})))
patch.setattr(mistakes, "_iter_visual_solution_chunks", stream)
state = {"mode": "recover", "attempts": 0, "vision_sizes": []}


def ocr(path, **kwargs):
    state["conversation_id"] = tasks.get(path.parent.name).conversation_id
    with Image.open(path) as image:
        state["vision_sizes"].append(list(image.size))
    return VisualProblemIR(problem_text="所选题目：求极限。", options=["A. 0", "B. 1", "C. 2", "D. 3"])


def transport(request):
    state["attempts"] += 1
    if state["mode"] == "payment":
        return httpx.Response(402, json={"error": {"message": "PRIVATE_PROVIDER_BODY"}})
    if state["attempts"] == 1:
        return httpx.Response(503, json={"error": {"message": "PRIVATE_PROVIDER_BODY"}})
    parts = [{"id": "qa", "choices": [{"index": 0, "delta": {"content": "恢复后的完整讲解。\n\n所选题目的答案为 $0$。"}, "finish_reason": None}]},
             {"id": "qa", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                          content="".join("data: " + json.dumps(part) + "\n\n" for part in parts) + "data: [DONE]\n\n")


model = DeepSeekChatOpenAI(model="deepseek-flash", api_key="offline-fixture", max_retries=0,
                         http_client=httpx.Client(transport=httpx.MockTransport(transport)))
patch.setattr(mistakes, "_ocr_image_with_kimi", ocr)
patch.setattr(mistakes, "_get_image_reasoning_llm", lambda **_: model)


@app.get("/api/qa/state")
def get_state():
    return state


@app.post("/api/qa/mode/{mode}")
def set_mode(mode: str):
    assert mode in {"recover", "payment"}
    state.update(mode=mode, attempts=0)
    return state


# Production SPA is already mounted; fixture control routes must precede it.
controls = [route for route in app.router.routes if getattr(route, "path", "").startswith("/api/qa/")]
app.router.routes[:] = controls + [route for route in app.router.routes if route not in controls]
uvicorn.run(app, host="127.0.0.1", port=int(os.environ["TEXA_QA_API_PORT"]), lifespan="off", access_log=False)
