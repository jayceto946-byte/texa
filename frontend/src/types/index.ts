/** TypeScript mapping for backend schemas.py */

export interface ChatRequest {
  question: string;
  book_name?: string;
  target_chapters?: string[];
}

export interface ChatEvent {
  stage: 'plan' | 'retrieve' | 'chapter' | 'generate' | 'done' | 'error';
  intent?: string;
  chapters?: string[];
  fast_path?: boolean;
  content_count?: number;
  has_teaching?: boolean;
  chunk?: string;
  replace?: boolean;
  done?: boolean;
  enriched?: boolean;
  message?: string;
  state?: {
    linked_concepts?: ConceptCandidate[];
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
  type: string;
  payload: Record<string, unknown>;
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
}
export interface ChatAgentCard {
  question: string;
  response: ReadOnlyAgentResponse;
}
