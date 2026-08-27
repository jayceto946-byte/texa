"""Pydantic request/response models for the FastAPI backend."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[dict] = None


class ChatRequest(BaseModel):
    question: str = Field(..., description="User question")
    book_name: str = Field(default="", description="Current book name")
    target_chapters: list[str] = Field(default_factory=list, description="Target chapters")
    subject: str = Field(default="", description="Selected subject")
    conversation_id: str = Field(default="", description="Conversation id for follow-up context")
    turn_id: str = Field(default="", description="Stable id shared by the user/assistant turn")
    answer_mode: str = Field(default="auto", description="auto/textbook_grounded/subject_general/global_general")


class FigureQuestionRequest(BaseModel):
    book_name: str = Field(..., min_length=1, max_length=200)
    figure_id: str = Field(..., min_length=1, max_length=100)
    question: str = Field(..., min_length=1, max_length=4000)
    bbox: list[float] | None = Field(default=None, description="Normalized image xyxy coordinates in [0, 1]")
    subject: str = Field(default="", max_length=100)
    conversation_id: str = Field(default="", max_length=100)
    turn_id: str = Field(default="", max_length=100)


class ConversationScopeRequest(BaseModel):
    subject: str
    book_name: str = ""
    source_subject: str = ""


class ConversationSplitTurnRequest(ConversationScopeRequest):
    turn_id: str


class SubjectRoutingFeedbackRequest(BaseModel):
    source_subject: str = ""
    target_subject: str
    action: str


class AnswerFeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    rating: str
    reasons: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=1000)


class LearningStateOperationRequest(BaseModel):
    operation: str
    learner_id: str = "local_default"
    book_name: str
    subject: str = ""
    conversation_id: str = ""
    source_id: str = ""
    goal_id: str = ""
    target_type: str = ""
    target_id: str = ""
    target_name: str = ""
    chapter_id: str = ""
    chapter_name: str = ""
    unit_id: str = ""
    unit_name: str = ""
    concept_names: list[str] = Field(default_factory=list)
    quality: Optional[int] = Field(default=None, ge=0, le=5)
    reason: str = Field(default="", max_length=500)


class ChatEvent(BaseModel):
    stage: str = Field(..., description="plan/retrieve/chapter/generate/done/error")
    intent: Optional[str] = None
    chapters: Optional[list[str]] = None
    fast_path: Optional[bool] = None
    planner_trace: Optional[dict] = None
    content_count: Optional[int] = None
    has_teaching: Optional[bool] = None
    chunk: Optional[str] = None
    replace: Optional[bool] = None
    done: Optional[bool] = None
    enriched: Optional[bool] = None
    message: Optional[str] = None
    conversation_id: Optional[str] = None
    turn_id: Optional[str] = None
    book_name: Optional[str] = None
    subject: Optional[str] = None
    subject_suggestion: Optional[dict] = None
    rewritten_question: Optional[str] = None
    resolution_action: Optional[str] = None
    use_textbook_context: Optional[bool] = None
    scope_reason: Optional[str] = None
    answer_mode: Optional[str] = None
    suggested_answer_mode: Optional[str] = None
    retrieval_status: Optional[str] = None
    retrieval_error: Optional[str] = None
    activity: Optional[dict] = None
    execution_event: Optional[dict] = None


class MistakeRecordOut(BaseModel):
    id: str
    book_id: str = ""
    question_text: str
    user_answer: str = ""
    correct_answer: str = ""
    source: str = ""
    subject: str = ""
    chapter: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    mistake_type: list[str] = Field(default_factory=list)
    difficulty: int = 3
    created_at: str = ""
    image_path: Optional[str] = None
    ocr_text: str = ""
    visual_ir: dict = Field(default_factory=dict)
    explanation: str = ""
    linked_concepts: list[dict] = Field(default_factory=list)
    review_history: list[dict] = Field(default_factory=list)
    next_review: Optional[str] = None
    interval: Optional[int] = None


class MistakeAddRequest(BaseModel):
    question_text: str
    user_answer: str = ""
    correct_answer: str = ""
    source: str = ""
    subject: str = ""
    chapter: str = ""
    tags: str = ""
    mistake_type: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=3, ge=1, le=5)
    image_path: Optional[str] = None
    ocr_text: str = ""
    visual_ir: dict = Field(default_factory=dict)
    explanation: str = ""


class MistakeListRequest(BaseModel):
    subject: str = ""
    chapter: str = ""
    tag: str = ""
    search_kw: str = ""
    limit: int = 50


class MistakeReviewRequest(BaseModel):
    id: str
    quality: int = Field(..., ge=0, le=5, description="Review quality 0-5")


class MistakeExplainRequest(BaseModel):
    id: str
    book_name: str = ""


class MistakeChatRequest(BaseModel):
    id: str
    question: str = "请重新讲解这道错题"
    user_answer: str = ""
    book_name: str = ""


class MistakeStatsOut(BaseModel):
    total: int
    due_today: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_tag: dict[str, int] = Field(default_factory=dict)
    by_difficulty: dict[int, int] = Field(default_factory=dict)


class WeakPointOut(BaseModel):
    name: str
    type: str
    count: int


class BookInfoOut(BaseModel):
    name: str
    chapter_count: int
    keyword_count: int = 0
    has_kg: bool = False


class BookSwitchRequest(BaseModel):
    name: str


class BookImportRequest(BaseModel):
    toc_pages: str = ""
    pre_read: bool = False


class PreReadStatusOut(BaseModel):
    running: bool = False
    done: int = 0
    total: int = 0
    status_text: str = ""


class KGGraphOut(BaseModel):
    book_name: str
    html_content: str = ""
    concept_count: int = 0
    exists: bool = False


class KGRefreshOut(BaseModel):
    success: bool
    html_content: str = ""
    message: str = ""
    concept_count: int = 0


class ExerciseRecordOut(BaseModel):
    id: str
    book_id: str = ""
    question_text: str
    answer: str = ""
    explanation: str = ""
    source: str = ""
    subject: str = ""
    chapter: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    question_type: str = ""
    difficulty: int = 3
    image_path: Optional[str] = None
    ocr_text: str = ""
    linked_concepts: list[dict] = Field(default_factory=list)
    origin_type: str = "manual"
    origin_id: str = ""
    status: str = "new"
    notes: str = ""
    last_practiced: Optional[str] = None
    practice_count: int = 0
    practice_history: list[dict] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class ExerciseAddRequest(BaseModel):
    question_text: str
    answer: str = ""
    explanation: str = ""
    source: str = ""
    subject: str = ""
    chapter: str = ""
    tags: str = ""
    question_type: str = ""
    difficulty: int = Field(default=3, ge=1, le=5)
    image_path: Optional[str] = None
    ocr_text: str = ""
    linked_concepts: list[dict] = Field(default_factory=list)
    origin_type: str = "manual"
    origin_id: str = ""
    status: str = "new"
    notes: str = ""


class ExerciseListRequest(BaseModel):
    subject: str = ""
    chapter: str = ""
    tag: str = ""
    search_kw: str = ""
    status: str = ""
    limit: int = 100


class ExerciseStatusRequest(BaseModel):
    id: str
    status: str


class ExerciseAnswerGenerateRequest(BaseModel):
    id: str


class ExerciseAnswerSaveRequest(BaseModel):
    id: str
    answer: str
    explanation: str = ""

class ExerciseFromMistakeRequest(BaseModel):
    mistake_id: str


class ExercisePracticeRequest(BaseModel):
    id: str
    user_answer: str = ""
    quality: int = Field(default=0, ge=0, le=5)
    note: str = ""
    add_to_mistake: bool = False


class ExerciseToMistakeRequest(BaseModel):
    id: str
    user_answer: str = ""
    mistake_type: list[str] = Field(default_factory=list)
class ExerciseCandidateOut(BaseModel):
    id: str
    question_text: str
    answer: str = ""
    explanation: str = ""
    source: str = ""
    subject: str = ""
    chapter: str = ""
    suggested_type: str = ""
    difficulty: int = 3
    tags: list[str] = Field(default_factory=list)
    linked_concepts: list[dict] = Field(default_factory=list)
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    needs_llm: bool = False
    needs_review: bool = True
    refined_by_llm: bool = False
    split_confidence: float = 0.0
    split_reasons: list[str] = Field(default_factory=list)
    validation_issues: list[str] = Field(default_factory=list)
    duplicate_of: str = ""


class ExerciseAnalyzeRequest(BaseModel):
    raw_text: str = ""
    candidates: list[str] = Field(default_factory=list)
    source: str = ""
    subject: str = ""
    chapter: str = ""
    known_concepts: list[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=500)
    use_llm: bool = False
    llm_max_items: int = Field(default=20, ge=1, le=100)

class TextbookExerciseAnalyzeRequest(BaseModel):
    book_name: str = ""
    subject: str = ""
    chapter: str = ""
    page_start: Optional[int] = Field(default=None, ge=1)
    page_end: Optional[int] = Field(default=None, ge=1)
    source_mode: str = "exercise_sections"
    limit: int = Field(default=200, ge=1, le=500)
    use_llm: bool = False
    llm_max_items: int = Field(default=20, ge=1, le=100)


class ExerciseBatchAddRequest(BaseModel):
    exercises: list[ExerciseAddRequest] = Field(default_factory=list)
    source_label: str = ""
    allow_duplicates: bool = False


class ExerciseImportRollbackRequest(BaseModel):
    batch_id: str


class ExercisePracticeSessionCreateRequest(BaseModel):
    subject: str = ""
    chapter: str = ""
    tag: str = ""
    status: str = ""
    limit: int = Field(default=20, ge=1, le=200)
    shuffle: bool = False


class ExercisePracticeSessionAnswerRequest(BaseModel):
    exercise_id: str
    user_answer: str = ""
    quality: int = Field(default=0, ge=0, le=5)
    note: str = ""
    add_to_mistake: bool = False
