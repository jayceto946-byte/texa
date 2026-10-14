export type NoteBlock = {
    block_id: string;
    type: 'heading' | 'paragraph' | 'list' | 'equation' | 'callout';
    role?: string | null;
    group_id?: string | null;
    data: {
        text?: string;
        level?: number;
        markdown?: string;
        latex?: string;
        annotation?: string;
        items?: string[];
        ordered?: boolean;
        tone?: string;
    };
    source_ref_ids: string[];
    evidence_ref_ids: string[];
    authorship?: string;
    source_alignment?: string;
    verification?: {
        status: string;
        reasons: string[];
    };
};
export type ChapterRef = {
    chapter_ref_id: string;
    book_id?: string;
    title_snapshot: string;
    book_name_snapshot?: string;
    resolution: string;
    canonical_hash?: string;
};
export type NoteContent = {
    title: string;
    abstract: string;
    subject: string;
    tags: string[];
    chapter_refs: ChapterRef[];
    blocks: NoteBlock[];
};
export type NoteQuality = {
    warning_hash: string;
    warnings: {
        reasons: string[];
        block_id?: string;
        source_ref_id?: string;
    }[];
    semantic_review: string;
};
export type Job = {
    id: string;
    status: string;
    stage: string;
    message: string;
    error?: string;
};
export type SourceSummary = {
    source_ref_id: string;
    id: string;
    role: string;
    created_at: string;
    included: boolean;
};
export type NoteDraft = {
    id: string;
    kind: string;
    status: string;
    draft_revision: number;
    conversation_id: string;
    content: (NoteContent & {
        quality: NoteQuality;
    }) | null;
    source_snapshot_ids: string[];
    base_note_id: string | null;
    base_note_revision: number | null;
    job_id: string | null;
    job?: Job | null;
    sources: SourceSummary[];
    chapter_options: ChapterRef[];
    published_note_id?: string;
    recovery_error?: string;
};
export type Note = NoteContent & {
    id: string;
    status: string;
    revision: number;
    updated_at: string;
    quality: NoteQuality;
    origins: {
        conversation_id: string;
        title_snapshot: string;
        captured_at: string;
    }[];
    chapter_availability?: Record<string, string>;
};
export type SourceDetail = {
    source: SourceSummary & {
        content: string;
        turn_id: string;
        delivery_status?: string;
        evidence_support_status?: string;
        learning_task: {
            status: string;
            verification?: {
                status?: string;
            };
        };
    };
    evidence: {
        evidence_ref_id: string;
        book_name?: string;
        index_version?: string;
        canonical_hash?: string;
        chunk_id?: string;
        snippet_status?: string;
        text?: string;
        snippet?: string;
        excerpt?: string;
        support_text?: string;
    }[];
    live_locator: {
        conversation_id: string;
        message_id: string;
    } | null;
    status: string;
};
export type Selection = {
    conversation_id: string;
    turn_ids?: string[];
    through_seq?: number;
};
export type Preflight = {
    selection: Selection;
    fingerprint: string;
    captured_at: string;
    turn_count: number;
    message_count: number;
    batches: number;
    warnings: NoteQuality['warnings'];
    turns: {
        turn_id: string;
        label: string;
    }[];
    existing_notes: {
        items: Note[];
    };
    existing_drafts: {
        items: NoteDraft[];
    };
};
