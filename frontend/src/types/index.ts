/** TypeScript mapping for backend schemas.py */

export type AnswerMode = 'auto' | 'textbook_grounded' | 'subject_general' | 'global_general' | 'subject_mismatch';

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

export interface ExecutionEvent {
  schema: 'texa.execution/v1' | string;
  seq: number;
  request_id: string;
  task_id?: string;
  run_id?: string;
  conversation_id?: string;
  turn_id?: string;
  operation_id: string;
  type: 'progress' | 'tool_call' | 'tool_result' | 'state_transition' | 'output_delta' | 'final' | 'error' | string;
  phase: string;
  status: 'started' | 'running' | 'completed' | 'failed' | 'skipped' | 'cancelled' | string;
  summary: string;
  label: string;
  kind: ActivityKind;
  elapsed_ms?: number;
  duration_ms?: number;
  payload?: Record<string, unknown>;
}

export interface ChatRequest {
  question: string;
  book_name?: string;
  target_chapters?: string[];
  answer_mode?: AnswerMode;
  suggested_answer_mode?: AnswerMode;
}

export interface ChatEvent {
  stage: 'context' | 'execution' | 'progress' | 'activity' | 'plan' | 'retrieve' | 'chapter' | 'generate' | 'waiting_for_input' | 'verify' | 'done' | 'error';
  intent?: string;
  chapters?: string[];
  fast_path?: boolean;
  planner_trace?: Record<string, unknown>;
  use_textbook_context?: boolean;
  scope_reason?: string;
  answer_mode?: AnswerMode;
  learning_task?: LearningTaskState;
  content_count?: number;
  has_teaching?: boolean;
  chunk?: string;
  replace?: boolean;
  done?: boolean;
  enriched?: boolean;
  message?: string;
  activity?: ChatActivity;
  execution_event?: ExecutionEvent;
  result?: {
    success?: boolean;
    explanation?: string;
    linked_concepts?: ConceptCandidate[];
    question_text?: string;
    mistake_id?: string;
    visual_ir?: Record<string, unknown>;
    learning_task?: LearningTaskState;
  };
  state?: {
    linked_concepts?: ConceptCandidate[];
    evidence_sources?: AssistantSource[];
    suggested_answer_mode?: AnswerMode;
    learning_task?: LearningTaskState;
  };
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
  label?: string;
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
export interface AgentToolSpec {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  read_only: boolean;
}

export interface AgentPendingAction {
  action_id?: string;
  type: string;
  payload: Record<string, unknown>;
  status?: 'pending' | 'confirmed' | 'rejected' | 'failed';
  result?: Record<string, unknown> | null;
  error?: string;
}

export interface AgentToolResult {
  success: boolean;
  message?: string;
  data?: unknown;
  pending_action?: AgentPendingAction | null;
}

export interface AgentToolCall {
  tool: string;
  args: Record<string, unknown>;
}

export interface AgentToolOutput {
  tool: string;
  args: Record<string, unknown>;
  result: AgentToolResult;
  required_outputs?: Array<{ key: string; path: string }>;
  satisfied_required_outputs?: string[];
  missing_required_outputs?: string[];
  timing?: {
    status: 'complete' | 'timeout' | 'error';
    elapsed_ms: number;
    timeout_seconds: number;
  };
}

export interface ReadOnlyAgentResponse {
  success: boolean;
  mode: 'read_only';
  answer: string;
  selected_tools: AgentToolCall[];
  tool_outputs: AgentToolOutput[];
  summary: {
    tool_counts: Record<string, number>;
    pending_actions: AgentPendingAction[];
    has_textbook_evidence: boolean;
    has_review_evidence: boolean;
  };
  execution_trace?: {
    total_elapsed_ms: number;
    budget_seconds: number;
    tools: Array<{
      tool: string;
      success: boolean;
      status: 'complete' | 'timeout' | 'error';
      elapsed_ms: number;
      timeout_seconds: number;
    }>;
    synthesis: {
      status: 'complete' | 'timeout' | 'error' | 'skipped';
      elapsed_ms: number;
      timeout_seconds: number;
      message?: string;
    };
  };
}
export interface ChatAgentCard {
  question: string;
  response: ReadOnlyAgentResponse;
}
