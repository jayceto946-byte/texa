import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, ExternalLink, ImagePlus, Loader2, Save, Upload } from 'lucide-react';
import { apiFetch, get, IMAGE_RECOGNITION_TIMEOUT_MS, IMAGE_SOLUTION_TIMEOUT_MS, post } from '../../api/client';
import ScopeSelector, { type ScopeBookOption } from '../ScopeSelector';
import { SimpleMarkdown } from './MarkdownMessage';

const MistakeQuickCaptureCard: React.FC<{ bookName: string; subject: string }> = ({ bookName, subject }) => {
  const navigate = useNavigate();
  const [availableBooks, setAvailableBooks] = useState<ScopeBookOption[]>([]);
  const [captureBookName, setCaptureBookName] = useState(bookName);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [questionText, setQuestionText] = useState('');
  const [userAnswer, setUserAnswer] = useState('');
  const [correctAnswer, setCorrectAnswer] = useState('');
  const [captureSubject, setCaptureSubject] = useState(subject || '数学');
  const [source, setSource] = useState('');
  const [chapter, setChapter] = useState('');
  const [tags, setTags] = useState('');
  const [difficulty, setDifficulty] = useState(3);
  const [explanation, setExplanation] = useState('');
  const [imagePath, setImagePath] = useState('');
  const [loading, setLoading] = useState<'ocr' | 'solve' | 'save' | ''>('');
  const [message, setMessage] = useState('');
  const [savedId, setSavedId] = useState('');

  useEffect(() => {
    setCaptureBookName(bookName);
  }, [bookName]);

  useEffect(() => {
    if (subject) setCaptureSubject(subject);
  }, [subject]);

  useEffect(() => {
    let alive = true;
    const loadBooks = async () => {
      try {
        const res = await get('/books/list');
        const rows = Array.isArray(res?.data) ? res.data : Array.isArray(res?.books) ? res.books : [];
        const next = rows.map((book: { name: string; subject?: string; displayName?: string; display_name?: string }) => ({ name: book.name, subject: book.subject || '', displayName: book.displayName || book.display_name }));
        if (alive) setAvailableBooks(next);
      } catch {
        if (alive) setAvailableBooks([]);
      }
    };
    loadBooks();
    const onBooksChanged = () => loadBooks();
    window.addEventListener('books:changed', onBooksChanged);
    return () => {
      alive = false;
      window.removeEventListener('books:changed', onBooksChanged);
    };
  }, []);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const onFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const next = event.target.files?.[0] || null;
    if (preview) URL.revokeObjectURL(preview);
    setFile(next);
    setPreview(next ? URL.createObjectURL(next) : '');
    setMessage('');
    setSavedId('');
  };

  const runImageAction = async (solve = false) => {
    if (!file) {
      setMessage('请先选择一张错题图片。');
      return;
    }
    setLoading(solve ? 'solve' : 'ocr');
    setMessage('');
    setSavedId('');
    if (solve) setExplanation('');
    const fd = new FormData();
    fd.append('file', file);
    if (solve) {
      fd.append('user_answer', userAnswer);
      fd.append('subject', captureSubject || subject);
      fd.append('tags', tags);
    }
    try {
      const res = await apiFetch(
        `/mistakes/${solve ? 'solve-image' : 'recognize-image'}`,
        { method: 'POST', body: fd },
        solve ? IMAGE_SOLUTION_TIMEOUT_MS : IMAGE_RECOGNITION_TIMEOUT_MS,
      );
      const data = await res.json();
      if (!data.success) {
        setMessage(data.message || '图片处理失败');
        return;
      }
      setMessage(solve ? '解题完成，可以保存到错题本查看完整题目与解答。' : (data.message || '识别完成，请校对 LaTeX 题干。'));
      if (data.image_path) setImagePath(data.image_path);
      if (data.ocr_text) setQuestionText(data.ocr_text);
      if (data.explanation) setExplanation(data.explanation);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading('');
    }
  };

  const saveMistake = async () => {
    if (!questionText.trim()) {
      setMessage('请先识别或手动填写题干。');
      return;
    }
    if (!explanation.trim()) {
      setMessage('请先点击“看图解题”，解题完成后再保存到错题本。');
      return;
    }
    setLoading('save');
    setMessage('');
    const selectedBook = captureBookName || bookName;
    const bookQuery = selectedBook ? `?book_name=${encodeURIComponent(selectedBook)}` : '';
    try {
      const res = await post(`/mistakes/add${bookQuery}`, {
        question_text: questionText,
        user_answer: userAnswer,
        correct_answer: correctAnswer,
        source,
        subject: captureSubject || subject,
        chapter,
        tags,
        difficulty,
        mistake_type: ['错题速录'],
        image_path: imagePath,
        ocr_text: questionText,
        explanation,
      });
      if (!res?.success) {
        setMessage(res?.message || '保存失败');
        return;
      }
      const nextId = res.id || res.data?.id || '';
      setSavedId(nextId);
      setMessage(res.message || '已保存到错题本。');
      window.dispatchEvent(new Event('mistakes:changed'));
      if (nextId) navigate(`/mistakes?mistake_id=${encodeURIComponent(nextId)}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading('');
    }
  };

  return (
    <div className="rounded-xl border border-border bg-[var(--surface-subtle)] p-4">
      <div className="mb-3 flex items-center gap-2 text-base font-semibold text-text-primary"><ImagePlus className="h-4 w-4 text-accent" />错题速录</div>
      <div className="grid gap-3 lg:grid-cols-[240px_minmax(0,1fr)]">
        <label className="flex min-h-[180px] cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-border bg-bg-card p-3 text-center text-sm text-text-secondary hover:border-accent/50">
          {preview ? <img src={preview} alt="错题预览" className="max-h-[220px] w-full rounded-lg object-contain" /> : <><Upload className="mb-2 h-6 w-6 text-accent" />上传/拍照错题图片</>}
          <input type="file" accept="image/*" capture="environment" onChange={onFileChange} className="hidden" />
        </label>
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={!file || Boolean(loading)} onClick={() => runImageAction(false)} className="rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs text-text-primary hover:border-accent/50 disabled:opacity-50">{loading === 'ocr' ? '识别中' : '识别题干'}</button>
            <button type="button" disabled={!file || Boolean(loading)} onClick={() => runImageAction(true)} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50">{loading === 'solve' ? '解题中' : '看图解题'}</button>
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            <textarea value={questionText} onChange={(e) => setQuestionText(e.target.value)} placeholder="OCR 题干，可手动校对" className="min-h-[130px] w-full rounded-lg border border-border bg-bg-card px-3 py-2 text-sm outline-none focus:border-accent" />
            <div className="max-h-[180px] overflow-y-auto rounded-lg border border-border bg-bg-card p-3">
              <div className="mb-2 text-xs font-medium text-text-secondary">LaTeX 预览</div>
              {questionText.trim() ? <SimpleMarkdown content={questionText} /> : <div className="text-sm text-text-secondary">识别题干后会在这里渲染公式。</div>}
            </div>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <textarea value={userAnswer} onChange={(e) => setUserAnswer(e.target.value)} placeholder="你的答案，可选" className="min-h-[70px] rounded-lg border border-border bg-bg-card px-3 py-2 text-sm outline-none focus:border-accent" />
            <textarea value={correctAnswer} onChange={(e) => setCorrectAnswer(e.target.value)} placeholder="正确答案，可选" className="min-h-[70px] rounded-lg border border-border bg-bg-card px-3 py-2 text-sm outline-none focus:border-accent" />
          </div>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-6">
            <div className="xl:col-span-2">
              <ScopeSelector subject={captureSubject} bookName={captureBookName} books={availableBooks} onSubjectChange={setCaptureSubject} onBookChange={setCaptureBookName} fullWidth width="wide" />
            </div>
            <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="来源" className="rounded-lg border border-border bg-bg-card px-3 py-2 text-sm outline-none focus:border-accent" />
            <input value={chapter} onChange={(e) => setChapter(e.target.value)} placeholder="章节" className="rounded-lg border border-border bg-bg-card px-3 py-2 text-sm outline-none focus:border-accent" />
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="标签，逗号分隔" className="rounded-lg border border-border bg-bg-card px-3 py-2 text-sm outline-none focus:border-accent" />
            <label className="flex items-center gap-2 rounded-lg border border-border bg-bg-card px-3 py-2 text-sm text-text-secondary">难度 {difficulty}<input type="range" min={1} max={5} value={difficulty} onChange={(e) => setDifficulty(Number(e.target.value))} className="min-w-0 flex-1 accent-accent" /></label>
          </div>
          {loading === 'solve' && <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-card px-3 py-2 text-xs text-text-secondary"><Loader2 className="h-3.5 w-3.5 animate-spin" />正在解题...</div>}
          {explanation && <div className="status-success flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"><CheckCircle2 className="h-4 w-4" />解题完成，完整解答将保存到错题本中查看。</div>}
          {explanation && <button type="button" disabled={Boolean(loading) || !questionText.trim()} onClick={saveMistake} className="inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">{loading === 'save' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}{loading === 'save' ? '保存中' : '保存到错题本'}</button>}
          {savedId && <button type="button" onClick={() => navigate(`/mistakes?mistake_id=${encodeURIComponent(savedId)}`)} className="inline-flex items-center gap-2 rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs text-text-primary hover:border-accent hover:text-accent"><ExternalLink className="h-3.5 w-3.5" />查看错题记录</button>}
          {message && <div className="rounded-lg border border-border bg-bg-card px-3 py-2 text-xs text-text-secondary">{message}</div>}
        </div>
      </div>
    </div>
  );
};

export default MistakeQuickCaptureCard;
