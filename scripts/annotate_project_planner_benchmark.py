"""Attach measurement limitations to the generated planner benchmark."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
json_path = ROOT / "benchmark_results" / "project_planners_sensor_20260801.json"
markdown_path = ROOT / "benchmark_results" / "project_planners_sensor_20260801.md"

data = json.loads(json_path.read_text(encoding="utf-8"))
data["measurement_notes"] = [
    "LangChain/DeepSeek 流式 usage 未返回 reasoning_tokens；记录中的 0 表示字段不可用，不表示没有思考。",
    "流式 usage 未返回缓存命中拆分；输入费用按全部 prompt tokens 缓存未命中保守估算，实际账单可能更低。",
    "首次 Flash 简单问答的端到端时间包含本地 embedding/Chroma 冷启动；模型生成速度应查看 llm_calls.elapsed_seconds。",
    "章节级 Chroma HNSW 多次报 Nothing found on disk；系统回退聚合索引。Teach planner 定位正确，但回退检索取到了第九章气电式传感器，导致两个教导回答主题错误。",
    "请求限定传感器短书，但证据标签出现传感器长书，表明聚合索引或证据元数据存在跨书混入。",
]
for result in data["results"]:
    result["usage"]["reasoning_tokens_available"] = False
    result["usage"]["cache_breakdown_available"] = False
    result["cost_cny"]["input_cost_assumption"] = "all_prompt_tokens_cache_miss"
json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

markdown = markdown_path.read_text(encoding="utf-8")
note = """## 计量与检索说明

- 流式 usage 未返回 reasoning token 与缓存拆分；reasoning=0 表示字段不可用，费用按全部输入缓存未命中保守估算。
- 首个 Flash 问答包含本地向量库冷启动；模型生成时间应参考审计 JSON 中各 llm_calls 的 elapsed_seconds。
- 章节级 Chroma HNSW 损坏触发聚合索引降级。Teach planner 章节定位正确，但实际取回气电式传感器内容，因此两份 Teach 回答均答非所问。
- 请求限定《传感器短书》，证据中却出现“传感器长书”标签，存在跨书证据混入。

"""
markdown = markdown.replace("## 简单问答", note + "## 简单问答", 1)
markdown = markdown.replace("，其中 reasoning 0", "，reasoning 字段未提供")
markdown_path.write_text(markdown, encoding="utf-8")
print("benchmark annotations updated")
