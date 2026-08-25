"""全局状态定义 — LangGraph AgentState"""
import operator
from typing import Annotated, TypedDict, Optional


class AgentState(TypedDict):
    # === 用户输入 ===
    user_input: str
    user_images: list[str]

    # === 用户画像 (长期) ===
    user_profile: dict
    learning_progress: dict
    long_term_memory: dict
    book_name: str
    subject: str
    conversation_id: str
    use_textbook_context: bool
    answer_mode: str
    scope_reason: str

    # === 会话上下文 ===
    messages: Annotated[list[dict], operator.add]
    active_evidence_sources: list[dict]
    active_evidence_ids: list[str]
    active_evidence_support: str
    active_evidence_invalidation_reason: str
    same_topic: bool
    requires_new_facet: bool
    previous_intent: str
    previous_book_name: str
    previous_subject: str
    conversation_context_seed: dict
    conversation_context_pack: dict
    learning_context_pack: dict
    tool_context_pack: dict  # bounded read-only results prepared by backend orchestration
    learning_task: dict
    required_outputs: list[dict]
    answer_verification: dict

    # === Planner 输出 ===
    intent: str                 # qa | teach | summarize | quiz | plan | cross_chapter
    _local_intent: str          # 本地分类器 hint（仅流式路径写入）
    _local_intent_hint: str
    _local_intent_locked: bool
    sub_tasks: list[dict]       # [{step, description, agent, chapter}]
    target_chapters: list[str]
    route_decision: str
    planner_trace: dict

    # === 检索结果 ===
    chapter_contents: dict      # {chapter_name: [docs]}
    retrieval_debug_items: list[dict]  # final prompt chunks with metadata for eval/debug
    evidence_items: list[dict]  # selected textbook evidence passed to generation
    evidence_sources: list[dict]  # human-readable evidence metadata returned to UI/persistence
    evidence_support: dict  # query-level support gate: supported | partial | insufficient | unavailable
    evidence_gate_applied: bool
    suggested_answer_mode: str
    citation_trace: dict
    index_stats: dict  # selected textbook index health
    concept_results: list[dict]  # 语义检索结果
    history_results: list[dict]  # 学习历史
    knowledge_graph_path: list[str]  # 知识图谱关联路径
    knowledge_graph_formulas: list[dict]  # 相关公式
    matched_concepts: list[str]  # 命中的概念名
    linked_concepts: list[dict]  # KG 对齐后的本轮关键概念
    retrieval_status: str  # ok | degraded
    retrieval_error: str
    retrieval_action: str  # none | reuse | delta | full
    retrieval_query: str
    reused_evidence_ids: list[str]
    new_evidence_ids: list[str]
    dropped_evidence_ids: list[str]

    # === 章节教学输出 ===
    teaching_content: str
    key_points: list[str]
    extracted_examples: list[dict]
    quiz_questions: list[dict]
    chapter_summary: str

    # === 综合生成输出 ===
    final_output: str
    output_type: str            # text | quiz | plan | mindmap
    context_budget: dict        # bounded generation-context telemetry

    # === 反馈 ===
    user_feedback: Optional[dict]
    mastery_update: dict
    next_review: Optional[str]

    # === 控制 ===
    error: str
    iteration: int
    max_iterations: int
