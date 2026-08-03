import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  BookOpenCheck,
  BrainCircuit,
  Camera,
  Check,
  ChevronDown,
  ChevronRight,
  Crop,
  ImagePlus,
  Loader2,
  Plus,
  Search,
  SlidersHorizontal,
  TrendingUp,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { apiFetch, del, get, post } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import ScopeSelector, { type ScopeBookOption } from '../components/ScopeSelector';
import { StatusBanner } from '../components/ui/AsyncState';
import { useChatContext } from '../contexts/ChatContext';
import {
  clamp,
  renderProcessedImage,
  type CropState,
  type ImageAdjust,
} from '../features/mistakes/imageProcessing';
import { MistakeMetric, MistakeRange } from '../features/mistakes/components/MistakePresentation';
import { useVisibleList } from '../hooks/useVisibleList';
import type { MistakeRecord, MistakeStats, WeakPoint } from '../types';
import { useMistakeReview } from '../features/mistakes/hooks/useMistakeReview';

const TABS = ['录入', '列表', '今日复习', '统计'] as const;
type Tab = (typeof TABS)[number];

type MistakeForm = {
  question_text: string;
  user_answer: string;
  correct_answer: string;
  source: string;
  subject: string;
  chapter: string;
  tags: string;
  difficulty: number;
  ocr_text: string;
  explanation: string;
  mistake_type: string[];
  image_path?: string;
};

type CropDragMode = 'draw' | 'move' | 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
type CropDragState = {
  mode: CropDragMode;
  originX: number;
  originY: number;
  startX: number;
  startY: number;
  startCrop: CropState;
};

const EMPTY_FORM: MistakeForm = {
  question_text: '',
  user_answer: '',
  correct_answer: '',
  source: '',
  subject: '数学',
  chapter: '',
  tags: '',
  difficulty: 3,
  ocr_text: '',
  explanation: '',
  mistake_type: [],
  image_path: undefined,
};

const DEFAULT_CROP: CropState = { x: 5, y: 8, w: 90, h: 78 };
const cropHandles: { mode: Exclude<CropDragMode, 'draw' | 'move'>; className: string; cursor: string }[] = [
  { mode: 'nw', className: '-left-2 -top-2', cursor: 'nwse-resize' },
  { mode: 'n', className: 'left-1/2 -top-2 -translate-x-1/2', cursor: 'ns-resize' },
  { mode: 'ne', className: '-right-2 -top-2', cursor: 'nesw-resize' },
  { mode: 'e', className: '-right-2 top-1/2 -translate-y-1/2', cursor: 'ew-resize' },
  { mode: 'se', className: '-bottom-2 -right-2', cursor: 'nwse-resize' },
  { mode: 's', className: '-bottom-2 left-1/2 -translate-x-1/2', cursor: 'ns-resize' },
  { mode: 'sw', className: '-bottom-2 -left-2', cursor: 'nesw-resize' },
  { mode: 'w', className: '-left-2 top-1/2 -translate-y-1/2', cursor: 'ew-resize' },
];
const DEFAULT_ADJUST: ImageAdjust = { brightness: 112, contrast: 138, sharpen: 35, grayscale: true };
const MISTAKE_TYPE_OPTIONS = ['概念不清', '公式记错', '计算错误', '思路卡住', '粗心/审题错误'];
const qualityLabels = ['完全不会', '很吃力', '勉强', '基本会', '熟练', '秒杀'];

function deriveMistakeTitle(record: MistakeRecord) {
  const raw = record.question_text || record.ocr_text || record.source || '未命名错题';
  const cleaned = raw
    .replace(/\$\$[\s\S]*?\$\$/g, ' ')
    .replace(/\$(?:\\.|[^$\\])*?\$/g, ' ')
    .replace(/\\[a-zA-Z]+(?:\{[^}]*\})?/g, ' ')
    .replace(/[[\]{}()*_#>`~|=+\\]/g, ' ')
    .split('\n')
    .map((line) => line.replace(/^\s*(题目|例题|解|证明|已知|求|问)[:：、.\s]*/g, '').trim())
    .find((line) => line.length >= 6);
  const title = cleaned || raw.replace(/\s+/g, ' ').trim();
  return title.length > 43 ? `${title.slice(0, 43)}...` : title;
}
const MistakesPage: React.FC = () => {
  const { bookName, setBookName, subject, setSubject } = useChatContext();
  const [books, setBooks] = useState<ScopeBookOption[]>([]);
  const [searchParams] = useSearchParams();
  const focusMistakeId = searchParams.get('mistake_id') || '';
  const bookQuery = bookName ? `?book_name=${encodeURIComponent(bookName)}` : '';
  const [activeTab, setActiveTab] = useState<Tab>('录入');
  const [entryStep, setEntryStep] = useState<1 | 2 | 3>(1);
  const [records, setRecords] = useState<MistakeRecord[]>([]);
  const [dueRecords, setDueRecords] = useState<MistakeRecord[]>([]);
  const [stats, setStats] = useState<MistakeStats | null>(null);
  const [weakPoints, setWeakPoints] = useState<WeakPoint[]>([]);
  const [pageLoading, setPageLoading] = useState(false);
  const [pageError, setPageError] = useState('');
  const [subjectFilter, setSubjectFilter] = useState(subject || '');
  const subjectQuery = subjectFilter.trim() ? `${bookQuery ? '&' : '?'}subject=${encodeURIComponent(subjectFilter.trim())}` : '';
  const scopedQuery = `${bookQuery}${subjectQuery}`;
  const [form, setForm] = useState<MistakeForm>(EMPTY_FORM);
  const [rawFile, setRawFile] = useState<File | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [rawPreview, setRawPreview] = useState('');
  const [imagePreview, setImagePreview] = useState('');
  const [cropOpen, setCropOpen] = useState(false);
  const [crop, setCrop] = useState<CropState>(DEFAULT_CROP);
  const [adjust, setAdjust] = useState<ImageAdjust>(DEFAULT_ADJUST);
  const [uploadMessage, setUploadMessage] = useState('');
  const [ocrLoading, setOcrLoading] = useState(false);
  const [solveLoading, setSolveLoading] = useState(false);
  const [explanation, setExplanation] = useState('');
  const [expandedId, setExpandedId] = useState('');
  const [savedRecord, setSavedRecord] = useState<MistakeRecord | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const cropStageRef = useRef<HTMLDivElement>(null);
  const cropDragRef = useRef<CropDragState | null>(null);
  const explanationRef = useRef('');
  const subjectSuggestions = Array.from(new Set([...records.map((item) => item.subject || '').filter(Boolean), ...books.map((book) => book.subject || '').filter(Boolean)]));
  const mistakeList = useVisibleList(records, 30, `${bookName}|${subjectFilter}`);
  const reviewList = useVisibleList(dueRecords, 20, `${bookName}|${subjectFilter}|review`);

  useEffect(() => {
    let cancelled = false;
    get('/books/list')
      .then((res) => {
        if (!cancelled && res?.success) setBooks(res.data || []);
      })
      .catch(() => {
        if (!cancelled) setBooks([]);
      });
    const onChanged = () => {
      get('/books/list')
        .then((res) => setBooks(res?.success ? res.data || [] : []))
        .catch(() => setBooks([]));
    };
    window.addEventListener('books:changed', onChanged);
    return () => {
      cancelled = true;
      window.removeEventListener('books:changed', onChanged);
    };
  }, []);

  const switchBook = async (name: string) => {
    if (!name) {
      setBookName('');
      return;
    }
    try {
      const res = await get(`/books/switch/${encodeURIComponent(name)}`);
      if (res?.success) {
        setBookName(res.data.name);
        if (res.data.subject) {
          setSubject(res.data.subject);
          setSubjectFilter(res.data.subject);
        }
      }
    } catch {
      setBookName(name);
    }
  };

  const updateSubjectFilter = (value: string) => {
    setSubjectFilter(value);
    setSubject(value);
  };

  const setField = <K extends keyof MistakeForm>(key: K, value: MistakeForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const loadList = useCallback(async () => {
    try {
      const res = await post(`/mistakes/list${bookQuery}`, { subject: subjectFilter.trim(), search_kw: '', limit: 50 });
      if (res?.success) setRecords(res.data || []);
    } catch (e) {
      console.error('loadList error:', e);
    }
  }, [bookQuery, subjectFilter]);

  const loadDue = useCallback(async () => {
    try {
      const res = await get(`/mistakes/due${scopedQuery}`);
      if (res?.success) setDueRecords(res.data || []);
    } catch (e) {
      console.error('loadDue error:', e);
    }
  }, [scopedQuery]);
  const loadOverview = useCallback(async () => {
    try {
      const res = await post(`/mistakes/overview${bookQuery}`, {
        subject: subjectFilter.trim(),
        search_kw: '',
        limit: 50,
      });
      if (res?.success) {
        setRecords(res.data?.records || []);
        setDueRecords(res.data?.due_records || []);
      }
    } catch (e) {
      console.error('loadOverview error:', e);
    }
  }, [bookQuery, subjectFilter]);

  const loadStats = useCallback(async () => {
    setPageLoading(true);
    setPageError('');
    try {
      const [statsRes, weakRes] = await Promise.all([
        get(`/mistakes/stats${scopedQuery}`),
        get(`/mistakes/weak-points${scopedQuery}`),
      ]);
      setStats(statsRes && typeof statsRes.total === 'number' ? statsRes : null);
      setWeakPoints(weakRes?.success ? weakRes.data || [] : []);
    } catch {
      setPageError('加载统计数据失败');
      setStats(null);
      setWeakPoints([]);
    } finally {
      setPageLoading(false);
    }
  }, [scopedQuery]);

  const {
    expandedReviewId,
    reviewMessage,
    showReviewMessage,
    expandReview,
    toggleReview,
    clearDeletedReview,
    handleReview,
  } = useMistakeReview({
    bookQuery,
    setRecords,
    setDueRecords,
    refreshDue: loadDue,
    refreshStats: loadStats,
  });

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (activeTab === '统计') loadStats();
  }, [activeTab, loadStats]);

  useEffect(() => {
    if (!focusMistakeId) return;
    setActiveTab('列表');
    setExpandedId(focusMistakeId);
    if (records.some((record) => record.id === focusMistakeId)) return;
    let cancelled = false;
    const loadFocusedMistake = async () => {
      try {
        const res = await get(`/mistakes/${encodeURIComponent(focusMistakeId)}${bookQuery}`);
        if (!cancelled && res?.success && res.data) {
          const record = res.data as MistakeRecord;
          setRecords((prev) => [record, ...prev.filter((item) => item.id !== record.id)]);
        }
      } catch (e) {
        console.error('loadFocusedMistake error:', e);
      }
    };
    loadFocusedMistake();
    return () => {
      cancelled = true;
    };
  }, [focusMistakeId, bookQuery, records]);

  useEffect(() => {
    return () => {
      if (rawPreview) URL.revokeObjectURL(rawPreview);
      if (imagePreview) URL.revokeObjectURL(imagePreview);
    };
  }, [rawPreview, imagePreview]);

  const acceptFile = (file: File) => {
    if (!file.type.startsWith('image/')) {
      setUploadMessage('请上传图片文件');
      return;
    }
    if (rawPreview) URL.revokeObjectURL(rawPreview);
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setRawFile(file);
    setImageFile(null);
    setRawPreview(URL.createObjectURL(file));
    setImagePreview('');
    setCrop(DEFAULT_CROP);
    setAdjust(DEFAULT_ADJUST);
    setCropOpen(true);
    setUploadMessage('');
    setExplanation('');
    explanationRef.current = '';
    setSavedRecord(null);
    setField('question_text', '');
    setField('ocr_text', '');
    setField('explanation', '');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextFile = e.target.files?.[0];
    if (nextFile) acceptFile(nextFile);
  };

  const applyImageProcessing = async () => {
    if (!rawFile) return;
    setUploadMessage('正在生成 OCR 工作图...');
    const processed = await renderProcessedImage(rawFile, crop, adjust);
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImageFile(processed.file);
    setImagePreview(processed.preview);
    setCropOpen(false);
    setUploadMessage('已生成 OCR 工作图，可以识别题干或看图解题。');
  };

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEntryStep(1);
    setRawFile(null);
    setImageFile(null);
    setUploadMessage('');
    setExplanation('');
    explanationRef.current = '';
    setSavedRecord(null);
    if (rawPreview) URL.revokeObjectURL(rawPreview);
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setRawPreview('');
    setImagePreview('');
    if (inputRef.current) inputRef.current.value = '';
  };

  const uploadForOcr = async (solve = false) => {
    if (!imageFile) {
      setUploadMessage('请先裁剪并生成 OCR 工作图');
      return;
    }
    setOcrLoading(!solve);
    setSolveLoading(solve);
    setUploadMessage('');
    if (!solve) {
      setExplanation('');
      explanationRef.current = '';
      setField('explanation', '');
    }

    const fd = new FormData();
    fd.append('file', imageFile);
    if (solve) {
      fd.append('user_answer', form.user_answer);
    }

    try {
      const res = await apiFetch(`/mistakes/${solve ? 'solve-image' : 'recognize-image'}`, { method: 'POST', body: fd });
      const data = await res.json();
      setUploadMessage(data.message || (data.success ? '处理完成' : '处理失败'));
      if (data.image_path) setField('image_path', data.image_path);
      if (data.ocr_text) {
        setEntryStep(2);
        setField('question_text', data.ocr_text);
        setField('ocr_text', data.ocr_text);
      }
      if (data.explanation) {
        explanationRef.current = data.explanation;
        setExplanation(data.explanation);
        setField('explanation', data.explanation);
      }
    } catch (e) {
      setUploadMessage(`图片处理失败: ${String(e)}`);
    } finally {
      setOcrLoading(false);
      setSolveLoading(false);
    }
  };

  const handleAdd = async () => {
    if (!form.question_text.trim()) return;
    const currentExplanation = form.explanation || explanation || explanationRef.current;
    const payload = { ...form, explanation: currentExplanation };
    try {
      const res = await post(`/mistakes/add${bookQuery}`, payload);
      if (!res?.success) {
        setUploadMessage(res?.message || '保存失败');
        return;
      }
      setUploadMessage(res.message || '已保存，解答已写入错题记录。');
      setForm((prev) => ({ ...prev, explanation: currentExplanation }));
      explanationRef.current = currentExplanation;
      if (currentExplanation) setExplanation(currentExplanation);
      const nextRecord = res.data ? { ...res.data, explanation: res.data.explanation || currentExplanation } : null;
      if (nextRecord) {
        setSavedRecord(nextRecord);
        setRecords((prev) => [nextRecord, ...prev.filter((item) => item.id !== nextRecord.id)]);
        setDueRecords((prev) => [nextRecord, ...prev.filter((item) => item.id !== nextRecord.id)]);
        setExpandedId(nextRecord.id);
        expandReview(nextRecord.id);
      }
      await loadDue();
    } catch (e) {
      setUploadMessage(`保存失败: ${String(e)}`);
    }
  };

  const deleteMistake = async (id: string) => {
    if (!window.confirm('确定删除这道错题吗？')) return;
    showReviewMessage('');
    setUploadMessage('');
    try {
      const res = await del(`/mistakes/${encodeURIComponent(id)}${bookQuery}`, 20000);
      if (!res?.success) {
        showReviewMessage(res?.message || '删除错题失败');
        return;
      }
      setRecords((prev) => prev.filter((item) => item.id !== id));
      setDueRecords((prev) => prev.filter((item) => item.id !== id));
      if (expandedId === id) setExpandedId('');
      clearDeletedReview(id);
      if (savedRecord?.id === id) setSavedRecord(null);
      showReviewMessage(res.message || '已删除错题');
      await loadList();
      await loadDue();
      if (activeTab === '统计') await loadStats();
    } catch (e) {
      showReviewMessage(e instanceof Error ? e.message : String(e));
    }
  };

  const toggleMistakeType = (type: string, checked: boolean) => {
    setForm((prev) => ({
      ...prev,
      mistake_type: checked ? [...prev.mistake_type, type] : prev.mistake_type.filter((item) => item !== type),
    }));
  };

  const renderExplanation = () => {
    if (!explanation && !solveLoading) return null;
    return (
      <section className="space-y-3 rounded-xl border border-border bg-bg-secondary/95 p-4">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <BrainCircuit className="h-4 w-4 text-accent" /> 解题讲解
        </div>
        {solveLoading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-text-secondary">
            <Loader2 className="h-4 w-4 animate-spin" /> 正在生成讲解...
          </div>
        ) : (
          <ChatMessage role="assistant" content={explanation} />
        )}
      </section>
    );
  };

  const renderMetadataAndSave = () => {
    return (
      <section className="space-y-4 rounded-xl border border-border bg-bg-card p-4">
        <div className="text-sm font-medium text-text-primary">归档信息</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input placeholder="来源，如 2024 真题 / 教材 P45" value={form.source} onChange={(e) => setField('source', e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none placeholder-text-secondary focus:border-accent" />
          <ScopeSelector
            subject={form.subject}
            onSubjectChange={(value) => setField('subject', value)}
            suggestions={subjectSuggestions}
            bookMode="hidden"
            label="所属科目"
            fullWidth
            width="wide"
          />
          <input placeholder="章节，可选" value={form.chapter} onChange={(e) => setField('chapter', e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none placeholder-text-secondary focus:border-accent" />
          <input placeholder="知识点标签，逗号分隔" value={form.tags} onChange={(e) => setField('tags', e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none placeholder-text-secondary focus:border-accent md:col-span-2" />
          <label className="flex items-center gap-3 rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary">
            <span className="flex-shrink-0 text-text-secondary">难度 {form.difficulty}</span>
            <input type="range" min={1} max={5} value={form.difficulty} onChange={(e) => setField('difficulty', Number(e.target.value))} className="w-full accent-accent" />
          </label>
        </div>
        <div className="space-y-2">
          <div className="text-sm font-medium text-text-primary">标记错因</div>
          <div className="flex flex-wrap gap-3">
            {MISTAKE_TYPE_OPTIONS.map((type) => (
              <label key={type} className="flex cursor-pointer items-center gap-1.5 text-sm text-text-primary">
                <input type="checkbox" checked={form.mistake_type.includes(type)} onChange={(e) => toggleMistakeType(type, e.target.checked)} className="accent-accent" />
                {type}
              </label>
            ))}
          </div>
        </div>
        {savedRecord && (
          <div className="rounded-lg border border-[#c9d8bd] bg-[#eef5e8] px-3 py-2 text-sm text-[var(--success)]">
            已保存成功，解答会在“列表”和“今日复习”中随错题一起展开显示。
          </div>
        )}
        <div className="flex justify-end gap-2">
          {savedRecord && (
            <button onClick={resetForm} className="flex items-center gap-2 rounded-xl border border-border px-4 py-2 text-sm text-text-primary hover:border-accent">
              <Plus className="h-4 w-4" /> 下一题
            </button>
          )}
          <button onClick={handleAdd} disabled={!form.question_text.trim()} className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-45">
            <Check className="h-4 w-4" /> {savedRecord ? '再次保存' : '保存错题'}
          </button>
        </div>
      </section>
    );
  };

  const renderSavedRecordDetail = (record: MistakeRecord, showCorrectAnswer = false) => (
    <div className="mt-4 space-y-4 border-t border-border pt-4">
      <section className="space-y-2">
        <div className="text-xs font-medium text-text-secondary">LaTeX 题干</div>
        <div className="rounded-xl border border-border bg-bg-secondary p-3">
          <ChatMessage role="assistant" content={record.question_text} linkedConcepts={record.linked_concepts || []} />
        </div>
      </section>
      <section className="space-y-2">
        <div className="text-xs font-medium text-text-secondary">对应概念</div>
        <div className="flex flex-wrap gap-2 rounded-xl border border-border bg-bg-secondary p-3">
          {record.linked_concepts?.length ? (
            record.linked_concepts.map((concept) => (
              <span key={concept.concept_id || concept.name} className="rounded border border-accent/30 bg-accent/10 px-2 py-1 text-xs font-medium text-accent-hover">
                {concept.name}
              </span>
            ))
          ) : (
            <span className="text-sm text-text-secondary">暂无对应概念</span>
          )}
        </div>
      </section>
      {showCorrectAnswer && (
        <section className="space-y-2">
          <div className="text-xs font-medium text-text-secondary">正确答案</div>
          <div className="rounded-xl border border-border bg-bg-secondary p-3">
            {record.correct_answer ? <ChatMessage role="assistant" content={record.correct_answer} linkedConcepts={record.linked_concepts || []} /> : <div className="text-sm text-text-secondary">暂无正确答案</div>}
          </div>
        </section>
      )}
      <section className="space-y-2">
        <div className="text-xs font-medium text-text-secondary">已保存解答</div>
        <div className="rounded-xl border border-border bg-bg-secondary p-3">
          {record.explanation ? <ChatMessage role="assistant" content={record.explanation} linkedConcepts={record.linked_concepts || []} /> : <div className="text-sm text-text-secondary">暂无已保存解答</div>}
        </div>
      </section>
      <div className="flex justify-end">
        <button onClick={() => deleteMistake(record.id)} className="flex items-center gap-1.5 rounded border border-[#e6b2a9] bg-[#fff1ed] px-3 py-1.5 text-xs text-[var(--danger)] hover:border-[var(--danger)]">
          <Trash2 className="h-3.5 w-3.5" /> 删除
        </button>
      </div>
    </div>
  );
  const pointToCropPercent = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = cropStageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return null;
    return {
      x: clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100),
      y: clamp(((event.clientY - rect.top) / rect.height) * 100, 0, 100),
    };
  };

  const startCropDrag = (mode: CropDragMode, event: React.PointerEvent<HTMLDivElement>) => {
    const point = pointToCropPercent(event);
    if (!point) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    cropDragRef.current = {
      mode,
      originX: point.x,
      originY: point.y,
      startX: point.x,
      startY: point.y,
      startCrop: crop,
    };
    if (mode === 'draw') {
      setCrop({ x: point.x, y: point.y, w: 1, h: 1 });
    }
  };

  const updateCropDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = cropDragRef.current;
    if (!drag) return;
    const point = pointToCropPercent(event);
    if (!point) return;
    event.preventDefault();

    const minSize = 5;
    const dx = point.x - drag.startX;
    const dy = point.y - drag.startY;
    const start = drag.startCrop;

    if (drag.mode === 'draw') {
      const left = clamp(Math.min(drag.originX, point.x), 0, 100 - minSize);
      const top = clamp(Math.min(drag.originY, point.y), 0, 100 - minSize);
      const right = clamp(Math.max(drag.originX, point.x), left + minSize, 100);
      const bottom = clamp(Math.max(drag.originY, point.y), top + minSize, 100);
      setCrop({ x: left, y: top, w: right - left, h: bottom - top });
      return;
    }

    if (drag.mode === 'move') {
      setCrop({
        ...start,
        x: clamp(start.x + dx, 0, 100 - start.w),
        y: clamp(start.y + dy, 0, 100 - start.h),
      });
      return;
    }

    let left = start.x;
    let top = start.y;
    let right = start.x + start.w;
    let bottom = start.y + start.h;

    if (drag.mode.includes('w')) left = clamp(start.x + dx, 0, right - minSize);
    if (drag.mode.includes('e')) right = clamp(start.x + start.w + dx, left + minSize, 100);
    if (drag.mode.includes('n')) top = clamp(start.y + dy, 0, bottom - minSize);
    if (drag.mode.includes('s')) bottom = clamp(start.y + start.h + dy, top + minSize, 100);

    setCrop({ x: left, y: top, w: right - left, h: bottom - top });
  };

  const finishCropDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!cropDragRef.current) return;
    event.preventDefault();
    cropDragRef.current = null;
  };

  const renderCropModal = () => {
    if (!cropOpen || !rawPreview) return null;
    return (
      <div className="app-overlay-enter fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
        <div className="app-large-dialog-enter grid max-h-[92vh] w-full max-w-6xl grid-cols-1 gap-4 overflow-y-auto rounded-xl border border-border bg-bg-primary p-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-text-primary"><Crop className="h-4 w-4 text-accent" /> 裁剪错题区域</div>
              <button onClick={() => setCropOpen(false)} className="rounded p-1 text-text-secondary hover:text-text-primary"><X className="h-5 w-5" /></button>
            </div>
            <div
              ref={cropStageRef}
              className="relative mx-auto max-h-[70vh] max-w-full touch-none select-none overflow-hidden rounded border border-border bg-bg-secondary"
              onPointerDown={(e) => startCropDrag('draw', e)}
              onPointerMove={updateCropDrag}
              onPointerUp={finishCropDrag}
              onPointerCancel={finishCropDrag}
            >
              <img src={rawPreview} alt="原图" draggable={false} className="max-h-[70vh] w-full select-none object-contain" style={{ filter: `brightness(${adjust.brightness}%) contrast(${adjust.contrast}%)${adjust.grayscale ? ' grayscale(100%)' : ''}` }} />
              <div
                className="absolute cursor-move border-2 border-accent bg-accent/10 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]"
                style={{ left: `${crop.x}%`, top: `${crop.y}%`, width: `${crop.w}%`, height: `${crop.h}%` }}
                onPointerDown={(e) => startCropDrag('move', e)}
              >
                <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded bg-accent/85 px-2 py-1 text-[11px] font-medium text-white shadow-sm">拖动选框</div>
                {cropHandles.map((handle) => (
                  <div
                    key={handle.mode}
                    className={`absolute h-3.5 w-3.5 rounded-full border-2 border-white bg-accent shadow-sm ${handle.className}`}
                    style={{ cursor: handle.cursor }}
                    onPointerDown={(e) => startCropDrag(handle.mode, e)}
                  />
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-border bg-bg-card px-3 py-2 text-xs leading-5 text-text-secondary">
              拖动蓝色选框移动区域，拖拽圆点调整大小；也可以在图片上重新拖出一个新区域。
            </div>
          </div>
          <div className="space-y-4 rounded-xl border border-border bg-bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-text-primary"><SlidersHorizontal className="h-4 w-4 text-accent" /> 扫描增强</div>
            <MistakeRange label="亮度" value={adjust.brightness} min={70} max={150} onChange={(v) => setAdjust((a) => ({ ...a, brightness: v }))} suffix="%" />
            <MistakeRange label="对比度" value={adjust.contrast} min={80} max={200} onChange={(v) => setAdjust((a) => ({ ...a, contrast: v }))} suffix="%" />
            <MistakeRange label="锐化" value={adjust.sharpen} min={0} max={100} onChange={(v) => setAdjust((a) => ({ ...a, sharpen: v }))} suffix="%" />
            <label className="flex items-center gap-2 text-sm text-text-primary"><input type="checkbox" checked={adjust.grayscale} onChange={(e) => setAdjust((a) => ({ ...a, grayscale: e.target.checked }))} className="accent-accent" />黑白扫描效果</label>
            <button onClick={applyImageProcessing} className="w-full rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover">使用该区域</button>
          </div>
        </div>
      </div>
    );
  };

  const hasEntryDraft = Boolean(rawFile || imageFile || form.question_text.trim() || form.user_answer.trim() || form.correct_answer.trim());

  return (
    <div className="flex h-full flex-col">
      <div className="app-page-header border-b border-border bg-bg-primary">
        <h2 className="app-page-title">错题本</h2>
        <ScopeSelector
          subject={subjectFilter}
          bookName={bookName}
          books={books}
          suggestions={subjectSuggestions}
          onSubjectChange={updateSubjectFilter}
          onBookChange={switchBook}
          allowAllSubjects
          align="right"
          width="wide"
        />
      </div>
      <div className="flex items-center border-b border-border bg-bg-secondary px-4">
        {TABS.map((tab) => (
          <button key={tab} onClick={() => setActiveTab(tab)} className={`border-b-2 px-4 py-3 text-sm font-medium transition-colors ${activeTab === tab ? 'border-accent text-accent' : 'border-transparent text-text-secondary hover:text-text-primary'}`}>{tab}</button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === '录入' && (
          <div className="mx-auto max-w-6xl space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3 border-y border-border px-1 py-2">
              <div className="flex items-center gap-2">
                {([1, 2, 3] as const).map((step) => (
                  <React.Fragment key={step}>
                    <button type="button" onClick={() => step < entryStep && setEntryStep(step)} disabled={step > entryStep} className={`flex items-center gap-2 px-2 py-1.5 text-sm ${entryStep === step ? 'font-medium text-accent' : step < entryStep ? 'text-text-primary hover:text-accent' : 'cursor-not-allowed text-text-secondary/55'}`}>
                      <span className={`flex h-5 w-5 items-center justify-center rounded border text-[11px] ${entryStep >= step ? 'border-accent/35 text-accent' : 'border-border'}`}>{step}</span>
                      {step === 1 ? '添加题目' : step === 2 ? '校对内容' : '归因保存'}
                    </button>
                    {step < 3 && <span className="h-px w-5 bg-border" />}
                  </React.Fragment>
                ))}
              </div>
              {hasEntryDraft && <button type="button" onClick={resetForm} className="type-caption text-text-secondary hover:text-[var(--danger)]">清空本题</button>}
            </div>

            {entryStep === 1 && (
              <section className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={(e) => { e.preventDefault(); setDragActive(false); const file = e.dataTransfer.files?.[0]; if (file) acceptFile(file); }}
                  className={`app-panel flex min-h-[190px] w-full flex-col items-center justify-center p-6 text-center ${dragActive ? 'border-accent bg-[var(--accent-softer)]' : 'hover:border-accent/60'}`}
                >
                  {imagePreview || rawPreview ? <img src={imagePreview || rawPreview} alt="错题预览" className="max-h-[270px] w-full object-contain" /> : <><ImagePlus className="mb-3 h-9 w-9 text-text-secondary" /><span className="type-section-title text-text-primary">上传错题图片</span><span className="type-caption mt-2 text-text-secondary">拖入图片，或点击调用文件选择与相机。</span></>}
                </button>
                <input ref={inputRef} type="file" accept="image/*" capture="environment" onChange={handleFileChange} className="hidden" />

                <div className="app-panel space-y-3 p-5">
                  <h3 className="type-section-title text-text-primary">{rawFile ? '图片已就绪' : '选择录入方式'}</h3>
                  <p className="type-caption leading-5 text-text-secondary">{rawFile ? '可调整题目区域，也可以直接识别。' : '拍照识别适合纸面题，识别后需要校对。'}</p>
                  <button onClick={() => inputRef.current?.click()} className="app-secondary-button w-full"><Camera className="h-4 w-4" />{rawFile ? '重新选择图片' : '选择图片或拍照'}</button>
                  {rawFile && <button onClick={() => setCropOpen(true)} className="app-secondary-button w-full"><Crop className="h-4 w-4" />调整题目区域</button>}
                  {imageFile && <button onClick={() => uploadForOcr(false)} disabled={ocrLoading || solveLoading} className="app-primary-button w-full disabled:opacity-45">{ocrLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}开始识别</button>}
                  {!rawFile && <button onClick={() => { setField('question_text', ''); setEntryStep(2); }} className="app-secondary-button w-full">手动录入</button>}
                  {uploadMessage && <StatusBanner kind={uploadMessage.includes('失败') ? 'error' : 'info'} title={uploadMessage} />}
                </div>
              </section>
            )}

            {entryStep === 2 && (
              <section className="app-panel overflow-hidden">
                <div className="border-b border-border px-5 py-4">
                  <h3 className="type-section-title text-text-primary">校对题目内容</h3>
                  <p className="type-caption mt-1 text-text-secondary">逐字检查题干、公式和符号；OCR 内容不会被直接当作最终题目。</p>
                </div>
                <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
                  <div className="space-y-3">
                    <label className="block type-caption text-text-secondary">题干</label>
                    <textarea value={form.question_text} onChange={(e) => setField('question_text', e.target.value)} placeholder="粘贴或输入完整题干，公式可使用 LaTeX" className="min-h-[220px] w-full rounded-xl border border-border bg-bg-primary px-3 py-2 type-body text-text-primary outline-none focus:border-accent" />
                    {form.question_text.trim() && <div className="rounded-xl border border-border bg-bg-secondary p-3"><ChatMessage role="assistant" content={form.question_text} /></div>}
                  </div>
                  <div className="space-y-3">
                    {(imagePreview || rawPreview) && <img src={imagePreview || rawPreview} alt="错题原图对照" className="max-h-[190px] w-full rounded-lg border border-border bg-bg-primary object-contain" />}
                    <textarea placeholder="你的答案，可选" value={form.user_answer} onChange={(e) => setField('user_answer', e.target.value)} className="min-h-[90px] w-full rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
                    <textarea placeholder="正确答案，可选" value={form.correct_answer} onChange={(e) => setField('correct_answer', e.target.value)} className="min-h-[90px] w-full rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
                    <button onClick={() => uploadForOcr(true)} disabled={!imageFile || ocrLoading || solveLoading} className="app-secondary-button w-full disabled:opacity-45">{solveLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <BrainCircuit className="h-4 w-4" />}根据图片生成讲解</button>
                  </div>
                </div>
                <div className="flex justify-between border-t border-border px-5 py-3">
                  <button onClick={() => setEntryStep(1)} className="app-secondary-button">返回添加题目</button>
                  <button onClick={() => setEntryStep(3)} disabled={!form.question_text.trim()} className="app-primary-button disabled:opacity-45">继续归因</button>
                </div>
              </section>
            )}

            {entryStep === 3 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div><h3 className="type-section-title text-text-primary">补充归档信息</h3><p className="type-caption mt-1 text-text-secondary">标记来源、知识点和错因，以便后续筛选与间隔复习。</p></div>
                  <button onClick={() => setEntryStep(2)} className="app-secondary-button">返回校对</button>
                </div>
                {renderExplanation()}
                {renderMetadataAndSave()}
                {uploadMessage && <StatusBanner kind={savedRecord ? 'success' : uploadMessage.includes('失败') ? 'error' : 'info'} title={uploadMessage} />}
              </div>
            )}
          </div>
        )}
        {activeTab === '列表' && (
          <div className="mx-auto max-w-5xl space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 text-text-secondary">
              <div className="flex items-center gap-2"><Search className="h-4 w-4" /><span className="text-sm">共 {records.length} 条错题</span></div>
              <div className="flex flex-wrap items-center gap-2">
                <ScopeSelector
                  subject={subjectFilter}
                  onSubjectChange={updateSubjectFilter}
                  suggestions={subjectSuggestions}
                  bookMode="hidden"
                  label="筛选科目"
                  allowAllSubjects
                  align="right"
                  width="compact"
                />
                {subjectFilter && <button onClick={() => updateSubjectFilter('')} className="rounded-xl border border-border px-3 py-1.5 text-sm hover:border-accent hover:text-text-primary">全部</button>}
                <button onClick={() => setActiveTab('录入')} className="flex items-center gap-2 rounded-xl border border-border px-3 py-1.5 text-sm hover:border-accent hover:text-text-primary"><Plus className="h-4 w-4" /> 新增</button>
              </div>
            </div>
            <div className="space-y-3">
              {mistakeList.visibleItems.map((record) => {
                const expanded = expandedId === record.id;
                return (
                  <div key={record.id} className="rounded-xl border border-border bg-bg-card p-4 transition-colors hover:border-accent/50">
                    <button type="button" onClick={() => setExpandedId(expanded ? '' : record.id)} className="flex w-full items-start justify-between gap-3 text-left">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                          {expanded ? <ChevronDown className="h-4 w-4 text-accent" /> : <ChevronRight className="h-4 w-4 text-text-secondary" />}
                          <span className="truncate">{deriveMistakeTitle(record)}</span>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-text-secondary">
                          <span>{record.subject || '未分类'}</span>
                          {record.chapter && <span>{record.chapter}</span>}
                          <span>{record.tags.join(', ') || '无标签'}</span>
                          <span className="text-accent">难度 {record.difficulty}</span>
                        </div>
                      </div>
                      <span className="flex-shrink-0 text-xs text-text-secondary">{record.id}</span>
                    </button>
                    {expanded && renderSavedRecordDetail(record)}
                  </div>
                );
              })}
              {mistakeList.hasMore && (
                <div className="flex justify-center pt-1">
                  <button onClick={mistakeList.showMore} className="rounded-xl border border-border bg-bg-primary px-4 py-2 text-sm text-text-secondary hover:border-accent hover:text-text-primary">
                    加载更多错题（已显示 {mistakeList.visibleCount} / {mistakeList.totalCount}）
                  </button>
                </div>
              )}
              {records.length === 0 && <div className="app-panel px-4 py-8 text-center text-text-secondary"><p>还没有错题。</p><button onClick={() => setActiveTab('录入')} className="app-secondary-button mt-3">录入第一道错题</button></div>}
            </div>
          </div>
        )}
        {activeTab === '今日复习' && (
          <div className="mx-auto max-w-5xl space-y-4">
            <div className="flex items-center gap-2 text-text-secondary"><BookOpenCheck className="h-4 w-4" /><span className="text-sm">今日待复习 {dueRecords.length} 道</span></div>
            {reviewMessage && <div className="rounded-lg border border-[#c9d8bd] bg-[#eef5e8] px-3 py-2 text-sm text-[var(--success)]">{reviewMessage}</div>}
            <div className="space-y-3">
              {reviewList.visibleItems.map((record) => {
                const expanded = expandedReviewId === record.id;
                return (
                  <div key={record.id} className="rounded-xl border border-border bg-bg-card p-4 transition-colors hover:border-accent/50">
                    <button type="button" onClick={() => toggleReview(record.id)} className="flex w-full items-start justify-between gap-3 text-left">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                          {expanded ? <ChevronDown className="h-4 w-4 text-accent" /> : <ChevronRight className="h-4 w-4 text-text-secondary" />}
                          <span className="truncate">{deriveMistakeTitle(record)}</span>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-text-secondary">
                          <span>{record.subject || '未分类'}</span>
                          {record.chapter && <span>{record.chapter}</span>}
                          <span>{record.tags.join(', ') || '无标签'}</span>
                          <span className="text-accent">难度 {record.difficulty}</span>
                        </div>
                      </div>
                      <span className="flex-shrink-0 text-xs text-text-secondary">间隔: {record.interval ?? 1} 天</span>
                    </button>
                    {expanded && renderSavedRecordDetail(record, true)}
                    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-4">
                      {[1, 2, 3, 4, 5].map((quality) => (
                        <button key={quality} onClick={() => handleReview(record.id, quality)} className="rounded border border-border bg-bg-primary px-3 py-1 text-xs transition-colors hover:border-accent hover:text-accent">
                          {quality} {qualityLabels[quality]}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
              {reviewList.hasMore && (
                <div className="flex justify-center pt-1">
                  <button onClick={reviewList.showMore} className="rounded-xl border border-border bg-bg-primary px-4 py-2 text-sm text-text-secondary hover:border-accent hover:text-text-primary">
                    加载更多复习题（已显示 {reviewList.visibleCount} / {reviewList.totalCount}）
                  </button>
                </div>
              )}
              {dueRecords.length === 0 && <div className="app-panel px-4 py-8 text-center text-text-secondary">今日没有到期错题，可以继续整理新错题或前往习题库练习。</div>}
            </div>
          </div>
        )}

        {activeTab === '统计' && (
          <div className="max-w-3xl space-y-6">
            {pageLoading && <div className="flex items-center justify-center gap-2 py-8 text-text-secondary"><Loader2 className="h-5 w-5 animate-spin" /> 加载统计中...</div>}
            {pageError && <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-[var(--danger)]">{pageError}</div>}
            {!pageLoading && !pageError && stats && <><div className="grid grid-cols-1 gap-4 sm:grid-cols-3"><MistakeMetric label="总错题数" value={stats.total ?? 0} tone="text-accent" /><MistakeMetric label="今日待复习" value={stats.due_today ?? 0} tone="text-[var(--danger)]" /><MistakeMetric label="错因类型" value={stats.by_type ? Object.keys(stats.by_type).length : 0} tone="text-[var(--success)]" /></div><div className="rounded-xl border border-border bg-bg-card p-4"><h3 className="mb-3 flex items-center gap-2 text-sm font-medium"><TrendingUp className="h-4 w-4 text-accent" /> 薄弱点 TOP 列表</h3><div className="space-y-2">{weakPoints.map((w, i) => <div key={`${w.type}-${w.name}`} className="flex items-center justify-between gap-3 text-sm"><span className="min-w-0 truncate text-text-primary">{i + 1}. <strong>{w.name || '未命名'}</strong><span className="ml-1 text-text-secondary">({w.type || '类型未知'})</span></span><span className="flex-shrink-0 font-medium text-accent">{w.count ?? 0} 次</span></div>)}{weakPoints.length === 0 && <div className="text-sm text-text-secondary">暂无薄弱点数据</div>}</div></div></>}
            {!pageLoading && !pageError && !stats && <div className="py-12 text-center text-text-secondary">暂无统计数据</div>}
          </div>
        )}
      </div>
      {renderCropModal()}
    </div>
  );
};

export default MistakesPage;
