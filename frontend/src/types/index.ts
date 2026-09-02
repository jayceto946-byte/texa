/** TypeScript mapping for backend schemas.py */

export type AnswerMode = 'auto' | 'textbook_grounded' | 'visual_grounded' | 'subject_general' | 'global_general' | 'subject_mismatch';

export interface CitationProvenance {
  status: 'model_aligned' | 'partially_aligned' | 'sources_attached' | string;
  model_citation_ids?: string[];
  source_attachment_origin?: 'system' | string;
  paragraph_alignment?: 'complete' | 'partial' | 'unverified' | string;
  automatic_citation_inserted?: boolean;
}

export type ActivityStatus = 'pending' | 'active' | 'completed' | 'skipped' | 'failed';
export type ActivityKind = 'analysis' | 'tool' | 'evidence' | 'reasoning' | 'generation' | 'memory' | 'system';

export interface LearningRequiredInput {
  type: string;
  name: string;
  reason: string;
  affects: string[];
  blocking: boolean;
  status: 'missing' | 'provided' | 'waived' | string;
}

export interface LearningTaskState {
  schema_version: string;
  id: string;
  task_type: 'qa' | 'visual_qa' | string;
  goal: string;
  status: 'running' | 'interrupted' | 'waiting_for_input' | 'waiting_for_confirmation' | 'degraded' | 'completed' | 'failed' | string;
  conversation_id?: string;
  turn_id?: string;
  answer_mode?: string;
  required_inputs: LearningRequiredInput[];
  required_outputs: Array<Record<string, unknown>>;
  artifacts?: Record<string, unknown>;
  verification?: Record<string, unknown>;
  terminal: boolean;
  interruptible: boolean;
  resumable: boolean;
  input_action_required: boolean;
  confirmation_required: boolean;
}

export interface ChatActivity {
  id: string;
  kind: ActivityKind;
  label: string;
  status: ActivityStatus;
  detail?: string;
  duration_ms?: number;
  meta?: Record<string, unknown>;
  seq?: number;
  operation_id?: string;
  event_type?: string;
  phase?: string;
  elapsed_ms?: number;
}

export type ExecutionEventType = 'progress' | 'state_transition' | 'tool_result' | 'output_delta' | 'final' | 'error';
export type ExecutionEventStatus = 'started' | 'running' | 'completed' | 'failed' | 'skipped' | 'cancelled';

export interface ExecutionEvent {
  schema: 'texa.execution/v1';
  seq: number;
  request_id: string;
  task_id: string;
  run_id: string;
  conversation_id: string;
  turn_id: string;
  operation_id: string;
  type: ExecutionEventType;
  phase: string;
  status: ExecutionEventStatus;
  summary: string;
  label: string;
  kind: ActivityKind;
  elapsed_ms: number;
  duration_ms?: number;
  payload: Record<string, unknown>;
}

/** Transport envelope for canonical execution events plus non-lifecycle business projections. */
export interface ExecutionStreamEnvelope {
  execution_event: ExecutionEvent;
  message_id?: string;
  intent?: string;
  chapters?: string[];
  fast_path?: boolean;
  planner_trace?: Record<string, unknown>;
  content_count?: number;
  book_name?: string;
  subject?: string;
  resolution_action?: 'continue' | 'clarify' | 'respond';
  subject_suggestion?: SubjectRouteSuggestion;
  rewritten_question?: string;
  use_textbook_context?: boolean;
  scope_reason?: string;
  answer_mode?: AnswerMode;
  suggested_answer_mode?: AnswerMode;
  learning_task?: LearningTaskState;
  retrieval_status?: string;
  retrieval_error?: string;
  result?: {
    success?: boolean;
    explanation?: string;
    linked_concepts?: ConceptCandidate[];
    question_text?: string;
    mistake_id?: string;
    visual_ir?: Record<string, unknown>;
    learning_task?: LearningTaskState;
    sources?: AssistantSource[];
    message_id?: string;
    conversation_id?: string;
    turn_id?: string;
    figure_id?: string;
    region?: number[] | null;
    citation_provenance?: CitationProvenance;
  };
  state?: {
    linked_concepts?: ConceptCandidate[];
    evidence_sources?: AssistantSource[];
    suggested_answer_mode?: AnswerMode;
    learning_task?: LearningTaskState;
  };
}

export interface ChatRequest {
  question: string;
  book_name?: string;
  target_chapters?: string[];
  answer_mode?: AnswerMode;
  suggested_answer_mode?: AnswerMode;
}

export interface ConceptCandidate {
  name: string;
  concept_id?: string;
  type?: string;
  confidence?: number;
  source?: string;
  evidence?: string;
  aliases?: string[];
  roles?: string[];
  definition?: string;
  related_concepts?: string[];
  source_chapters?: string[];
}

export interface AssistantSource {
  id?: string;
  chunk_id?: string;
  book_name?: string;
  chapter?: string;
  section_title?: string;
  section_path?: string[];
  chunk_index?: number;
  heading_level?: number;
  page_idx?: number;
  page_start?: number | null;
  page_end?: number | null;
  provenance_schema?: string;
  index_version?: string;
  canonical_hash?: string;
  source_block_ids?: string[];
  source_locations?: Array<{
    block_id: string;
    source_kind: string;
    source_file: string;
    page_start: number | null;
    page_end: number | null;
    bbox: number[];
    bbox_space: string;
    bbox_format: string;
    bbox_units: string;
  }>;
  source_kind?: string;
  source_file?: string;
  bbox?: number[];
  label?: string;
  figure_id?: string;
  block_id?: string;
  caption?: string;
  text?: string;
  asset_url?: string;
  pdf_url?: string;
}

export interface VisualRegion {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface FigureArtifact {
  figure_id: string;
  book_name: string;
  caption: string;
  source_text?: string;
  page?: number | null;
  page_idx?: number | null;
  page_bbox: number[];
  bbox_space: 'page' | string;
  bbox_format: 'xyxy' | string;
  bbox_units?: string;
  section_path: string[];
  source_file: string;
  source_kind: string;
  asset_status: 'ready' | 'missing' | 'invalid' | string;
  image_width: number;
  image_height: number;
  image_url: string;
  pdf_url: string;
  match_scope?: 'caption' | 'section' | 'nearby_text' | string;
}

export interface ConceptWiki {
  concept: {
    concept_id: string;
    canonical_name: string;
    aliases: string[];
    roles: string[];
    confidence: number;
    occurrence_count: number;
  };
  definition: string;
  prerequisites: string[];
  extensions: string[];
  related_formulas: { formula_id: string; formula_latex: string }[];
  source_chapters: string[];
}

export interface ReviewHistoryItem {
  date: string;
  quality: number;
  interval: number;
  easiness?: number;
  next_review?: string;
}

export interface MistakeRecord {
  id: string;
  question_text: string;
  user_answer: string;
  correct_answer: string;
  source: string;
  subject: string;
  chapter?: string;
  tags: string[];
  mistake_type: string[];
  difficulty: number;
  created_at: string;
  image_path?: string;
  ocr_text?: string;
  visual_ir?: Record<string, unknown>;
  explanation?: string;
  linked_concepts?: ConceptCandidate[];
  review_history?: ReviewHistoryItem[];
  next_review?: string;
  interval?: number;
}

export interface MistakeStats {
  total: number;
  due_today: number;
  by_type: Record<string, number>;
  by_tag: Record<string, number>;
  by_difficulty: Record<number, number>;
}

export interface WeakPoint {
  name: string;
  type: string;
  count: number;
}

export interface BookInfo {
  name: string;
  book_id?: string;
  displayName?: string;
  subject?: string;
  chapter_count: number;
  chapters?: { title: string; page: number }[];
}

export interface ApiResponse<T = unknown> {
  success: boolean;
  message?: string;
  data?: T;
}

export interface ExerciseRecord {
  id: string;
  question_text: string;
  answer: string;
  explanation: string;
  source: string;
  subject: string;
  chapter?: string;
  tags: string[];
  question_type: string;
  difficulty: number;
  image_path?: string;
  ocr_text?: string;
  linked_concepts?: ConceptCandidate[];
  origin_type: string;
  origin_id: string;
  status: string;
  notes: string;
  last_practiced?: string;
  practice_count: number;
  practice_history?: { date: string; quality: number; user_answer?: string; note?: string }[];
  created_at: string;
  updated_at: string;
}

export interface ExerciseStats {
  total: number;
  by_type: Record<string, number>;
  by_tag: Record<string, number>;
  by_status: Record<string, number>;
}
export interface ExerciseCandidate {
  id: string;
  question_text: string;
  answer: string;
  explanation: string;
  source: string;
  subject: string;
  chapter: string;
  suggested_type: string;
  difficulty: number;
  tags: string[];
  linked_concepts?: ConceptCandidate[];
  confidence: number;
  reasons: string[];
  needs_llm: boolean;
  needs_review: boolean;
  refined_by_llm?: boolean;
  split_confidence?: number;
  split_reasons?: string[];
  validation_issues?: string[];
  duplicate_of?: string;
}

export interface ExerciseImportBatch {
  id: string;
  source_label: string;
  exercise_ids: string[];
  skipped: Array<{ origin_id: string; duplicate_of: string }>;
  created_at: string;
  status: 'active' | 'rolled_back';
  rolled_back_at?: string;
}

export interface ExercisePracticeSession {
  id: string;
  exercise_ids: string[];
  filters: Record<string, string>;
  shuffle: boolean;
  seed: number;
  current_index: number;
  status: 'active' | 'paused' | 'completed' | 'abandoned' | 'replaced';
  results: Record<string, {
    exercise_id: string;
    user_answer: string;
    quality: number;
    note?: string;
    mistake_id?: string;
    answered_at: string;
  }>;
  current_exercise?: ExerciseRecord | null;
  summary: {
    total: number;
    answered: number;
    remaining: number;
    mastered: number;
    struggling: number;
    average_quality: number;
  };
}

export type SystemHealthStatus = 'healthy' | 'degraded' | 'error';

export interface SystemHealthComponent {
  status: SystemHealthStatus;
  message: string;
  details: Record<string, unknown>;
}

export interface SystemHealthResponse {
  status: SystemHealthStatus;
  book_name: string;
  components: Record<string, SystemHealthComponent>;
}
export interface LearningReport {
  book_name: string;
  subject: string;
  range_days: number;
  start_date: string;
  end_date: string;
  summary: Record<string, number>;
  top_concepts: { name: string; count: number }[];
  weak_points: { name: string; count: number }[];
  recent_questions: { time: string; question: string }[];
  suggestions: string[];
}

export interface ChatReportCard {
  kind: 'daily' | 'weekly';
  report: LearningReport;
}


export interface ChatChapterHighlightCard {
  book_name: string;
  chapter_id: string;
  chapter_title: string;
  section_id?: string;
  section_title?: string;
  scope_type?: 'chapter' | 'section' | string;
  scope_title?: string;
  markdown: string;
  generated_at?: string;
}
export interface ChatExerciseCard {
  record: ExerciseRecord;
}

export interface SubjectRouteSuggestion {
  target_subject: string;
  target_book_name: string;
  current_subject: string;
  current_book_name: string;
  confidence: number;
  reason: string;
}
export interface ChatUtilityCard {
  kind: 'mistake_quick_capture';
}
export interface AgentPendingAction {
  action_id?: string;
  type: string;
  payload: Record<string, unknown>;
  status?: 'pending' | 'confirmed' | 'rejected' | 'failed';
  result?: Record<string, unknown> | null;
  error?: string;
}
