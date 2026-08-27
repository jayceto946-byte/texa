import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Archive, BookOpen, CheckCircle2, ChevronDown, ChevronRight, FolderOpen, MoreHorizontal, Pencil, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import ScopeSelector from '../ScopeSelector';

export type LibrarySubject = { name: string; children: string[] };
export type BookReadiness = {
  technical?: { status?: 'ready' | 'degraded' | 'missing'; vector_ready?: boolean; lexical_ready?: boolean; chunk_count?: number; index_version?: string };
  canonical?: { status?: 'ready' | 'needs_review' | 'invalid' | 'unavailable'; warning_count?: number; error_count?: number; block_count?: number };
  semantic?: { status?: 'verified' | 'unverified'; release_status?: string; case_count?: number; human_case_count?: number; generated_probe_cases?: number };
};
export type LibraryBook = { name: string; book_id?: string; storage_name?: string; display_name?: string; lifecycle_status?: 'active' | 'archived'; subject?: string; path?: string; has_pdf?: boolean; chapter_count?: number; book_role?: 'standalone' | 'core' | 'reference'; rag_priority?: number; resource_group?: string; readiness?: BookReadiness };

type Props = {
  subjects: LibrarySubject[]; books: LibraryBook[]; selectedSubjectIndex: number; selectedChildIndex: number | null;
  onSelect: (subjectIndex: number, childIndex: number | null) => void; onAddSubject: () => void; onAddChild: (subjectIndex: number) => void;
  onRenameSubject: (index: number, name: string) => void; onRenameChild: (index: number, name: string) => void;
  onDeleteSubject: (index: number) => void; onDeleteChild: (index: number) => void;
  onRefresh: () => void; onMoveBook: (name: string, target: string) => void;
  onSetRole: (name: string, role: 'standalone' | 'core' | 'reference') => void; onSetResourceGroup: (name: string, resourceGroup: string) => void;
  onSwitchBook: (name: string) => void; onArchiveBook: (name: string) => void; onRestoreBook: (name: string) => void;
  onRenameBook: (name: string, displayName: string) => void; onReindexBook: (name: string) => void; reindexingBook?: string; currentBookName?: string;
};

const subjectPath = (parent = '', child = '') => child ? `${parent}/${child}` : parent;
const belongsTo = (book: LibraryBook, parent: string, child = '') => {
  const value = (book.subject || '').trim();
  if (!parent) return !value;
  if (child) return value === subjectPath(parent, child) || value === child;
  return value === parent || value.startsWith(`${parent}/`);
};

export default function LibraryWorkbench(props: Props) {
  const { subjects, books, selectedSubjectIndex, selectedChildIndex, onSelect } = props;
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [listMode, setListMode] = useState<'active' | 'archived'>('active');
  const [renamingCategory, setRenamingCategory] = useState(false);
  const [renameDraft, setRenameDraft] = useState('');
  const subject = selectedSubjectIndex >= 0 ? subjects[selectedSubjectIndex] || null : null;
  const child = subject && selectedChildIndex !== null ? subject.children[selectedChildIndex] || '' : '';
  const activeBooks = useMemo(() => books.filter((book) => book.lifecycle_status !== 'archived'), [books]);
  const archivedBooks = useMemo(() => books.filter((book) => book.lifecycle_status === 'archived'), [books]);
  const currentBooks = useMemo(() => subject ? activeBooks.filter((book) => belongsTo(book, subject.name, child)) : activeBooks.filter((book) => !(book.subject || '').trim()), [activeBooks, subject, child]);
  const parentHasBooks = subject ? activeBooks.some((book) => belongsTo(book, subject.name)) : false;
  const selectedHasBooks = Boolean(subject && (child ? activeBooks.some((book) => belongsTo(book, subject.name, child)) : parentHasBooks));
  const categoryName = child || subject?.name || '未分类教材';

  useEffect(() => {
    setRenamingCategory(false);
    setRenameDraft(categoryName);
  }, [categoryName, selectedSubjectIndex, selectedChildIndex]);

  const select = (subjectIndex: number, childIndex: number | null) => {
    onSelect(subjectIndex, childIndex);
    setListMode('active');
    if (subjectIndex >= 0) setExpanded((value) => ({ ...value, [subjectIndex]: true }));
  };

  const commitCategoryRename = () => {
    const next = renameDraft.trim();
    if (!subject || !next) return;
    if (selectedChildIndex === null) props.onRenameSubject(selectedSubjectIndex, next);
    else props.onRenameChild(selectedChildIndex, next);
    setRenamingCategory(false);
  };

  return (
    <section className="library-manager">
      <div className="library-workbench">
        <aside className="library-tree" aria-label="教材分类">
          <div className="library-tree-heading"><span>分类</span><button onClick={props.onAddSubject} className="library-tree-add" title="添加学科"><Plus className="h-4 w-4" />添加学科</button></div>
          <div className="library-tree-list">
            {subjects.map((item, index) => {
              const open = expanded[index] ?? selectedSubjectIndex === index;
              const active = selectedSubjectIndex === index && selectedChildIndex === null;
              const count = activeBooks.filter((book) => belongsTo(book, item.name)).length;
              return <div key={`${item.name}-${index}`}>
                <div className={`library-tree-parent ${active ? 'is-active' : ''}`}>
                  <button onClick={() => setExpanded((value) => ({ ...value, [index]: !open }))} className="library-tree-disclosure" aria-label={open ? '折叠' : '展开'}>{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button>
                  <button onClick={() => select(index, null)} className="library-tree-item"><FolderOpen className="h-4 w-4" /><span>{item.name}</span><span className="library-tree-count">{count}</span></button>
                </div>
                {open && <div className="library-tree-children">
                  {item.children.map((childName, childIndex) => <button key={`${childName}-${childIndex}`} onClick={() => select(index, childIndex)} className={`library-tree-child ${selectedSubjectIndex === index && selectedChildIndex === childIndex ? 'is-active' : ''}`}><span>{childName}</span><span className="library-tree-count">{activeBooks.filter((book) => belongsTo(book, item.name, childName)).length}</span></button>)}
                  <button onClick={() => { select(index, null); props.onAddChild(index); }} className="library-tree-child is-add"><Plus className="h-4 w-4" />添加科目</button>
                </div>}
              </div>;
            })}
            <button onClick={() => select(-1, null)} className={`library-tree-uncategorized ${selectedSubjectIndex < 0 ? 'is-active' : ''}`}><Archive className="h-4 w-4" /><span>未分类</span><span className="library-tree-count">{activeBooks.filter((book) => !(book.subject || '').trim()).length}</span></button>
          </div>
        </aside>

        <main className="library-content">
          <header className="library-category-header">
            <div className="library-category-identity">
              {renamingCategory ? <div className="library-inline-rename">
                <input autoFocus value={renameDraft} onChange={(event) => setRenameDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') commitCategoryRename(); if (event.key === 'Escape') setRenamingCategory(false); }} aria-label={`${child ? '科目' : '学科'}名称`} />
                <button onClick={commitCategoryRename} className="app-secondary-button">确定</button>
                <button onClick={() => setRenamingCategory(false)} className="app-icon-button" aria-label="取消重命名"><X className="h-4 w-4" /></button>
              </div> : <div><h3>{categoryName}</h3><p>{currentBooks.length} 本教材{child && subject ? ` · ${subject.name} / ${child}` : ''}</p></div>}
              {subject && !renamingCategory && <div className="library-category-actions">
                <button disabled={selectedHasBooks} onClick={() => { setRenameDraft(categoryName); setRenamingCategory(true); }} className="app-ghost-button" title={selectedHasBooks ? '请先移出该分类中的教材' : '重命名分类'}><Pencil className="h-3.5 w-3.5" />重命名</button>
                <button disabled={selectedHasBooks} onClick={() => selectedChildIndex === null ? props.onDeleteSubject(selectedSubjectIndex) : props.onDeleteChild(selectedChildIndex)} className="library-delete-category" title={selectedHasBooks ? '请先移出该分类中的教材' : '删除分类'}><Trash2 className="h-3.5 w-3.5" />删除分类</button>
              </div>}
            </div>
            <div className="library-header-tools">
              <div className="library-list-filter" role="group" aria-label="教材状态"><button aria-pressed={listMode === 'active'} onClick={() => setListMode('active')}>活跃 <span>{activeBooks.length}</span></button><button aria-pressed={listMode === 'archived'} onClick={() => setListMode('archived')}>已归档 <span>{archivedBooks.length}</span></button></div>
              <button onClick={props.onRefresh} className="app-icon-button" title="刷新教材" aria-label="刷新教材"><RefreshCw className="h-4 w-4" /></button>
            </div>
          </header>

          {listMode === 'active' ? <div className="library-book-list">
            <div className="library-list-columns" aria-hidden="true"><span>教材</span><span>索引与 IR</span><span>归属与资料组</span><span>角色</span><span>操作</span></div>
            {currentBooks.map((book) => <BookRow key={book.book_id || book.name} book={book} active={props.currentBookName === book.name} subjects={subjects} reindexing={props.reindexingBook === book.name} onMove={(value) => props.onMoveBook(book.name, value)} onSetRole={(role) => props.onSetRole(book.name, role)} onSetResourceGroup={(group) => props.onSetResourceGroup(book.name, group)} onSwitch={() => props.onSwitchBook(book.name)} onReindex={() => props.onReindexBook(book.name)} onRename={() => props.onRenameBook(book.name, book.display_name || book.name)} onArchive={() => props.onArchiveBook(book.name)} />)}
            {!currentBooks.length && <div className="library-empty"><BookOpen className="h-5 w-5" /><strong>这里还没有教材</strong><span>移动已有教材到此处，或导入新教材。</span></div>}
          </div> : <ArchivedBookList books={archivedBooks} onRestore={props.onRestoreBook} />}
        </main>
      </div>
    </section>
  );
}

const ROLE_OPTIONS = [{ value: 'core' as const, label: '主要' }, { value: 'reference' as const, label: '辅助' }, { value: 'standalone' as const, label: '独立' }];
const roleGuidance = (role: 'standalone' | 'core' | 'reference') => role === 'reference' ? '辅助教材用于补充主要教材内容' : role === 'core' ? '主要教材在回答时优先参考' : '独立教材不加入资料组';

function ReadinessSummary({ book }: { book: LibraryBook }) {
  const technical = book.readiness?.technical;
  const canonical = book.readiness?.canonical;
  const technicalReady = technical?.status === 'ready';
  const canonicalReady = canonical?.status === 'ready';
  const canonicalLabel = canonical?.status === 'needs_review' ? `待复核 · ${canonical.warning_count || 0} 项` : canonical?.status === 'invalid' ? '不可用' : canonicalReady ? '完整' : '无';
  return <div className="library-readiness" title={book.readiness?.semantic?.status === 'verified' ? `语义质量已验证 · ${book.readiness.semantic.human_case_count || 0} 个人工案例` : '语义质量尚未人工验证'}>
    <span className={technicalReady ? 'is-ready' : 'is-warning'}>{technicalReady ? <CheckCircle2 /> : <AlertTriangle />}<b>检索</b>{technicalReady ? `可用 · ${technical?.chunk_count || 0} 片段` : technical?.status === 'degraded' ? '部分可用' : '需重建'}</span>
    <span className={canonicalReady ? 'is-ready' : canonical?.status === 'needs_review' || canonical?.status === 'invalid' ? 'is-warning' : ''}>{canonicalReady ? <CheckCircle2 /> : <AlertTriangle />}<b>IR</b>{canonicalLabel}</span>
  </div>;
}

function BookRow({ book, active, subjects, reindexing, onMove, onSetRole, onSetResourceGroup, onSwitch, onReindex, onRename, onArchive }: { book: LibraryBook; active: boolean; subjects: LibrarySubject[]; reindexing: boolean; onMove: (target: string) => void; onSetRole: (role: 'standalone' | 'core' | 'reference') => void; onSetResourceGroup: (group: string) => void; onSwitch: () => void; onReindex: () => void; onRename: () => void; onArchive: () => void }) {
  const role = book.book_role || 'standalone';
  return <article className="library-book-row">
    <div className="library-book-identity"><div><h4>{book.display_name || book.name}</h4>{active && <span className="library-current-status">当前</span>}</div><p>{book.has_pdf ? 'PDF' : 'OCR / Markdown'} · {book.chapter_count || 0} 章</p></div>
    <ReadinessSummary book={book} />
    <div className="library-book-scope">
      <div className="library-subject-field"><span>归属</span><ScopeSelector subject={book.subject || ''} subjectTree={subjects} onSubjectChange={onMove} bookMode="hidden" width="normal" label={`${book.display_name || book.name}教材归属`} placeholder="未分类" className="library-subject-selector" /></div>
      {role === 'standalone' ? <div className="library-resource-group-static"><span>资料组</span><strong>不加入资料组</strong></div> : <label><span>资料组</span><input defaultValue={book.resource_group || ''} placeholder={book.subject ? `默认：${book.subject}` : '输入资料组'} onBlur={(event) => onSetResourceGroup(event.target.value.trim())} /></label>}
    </div>
    <div className="library-role-control" role="group" aria-label={`${book.display_name || book.name}的教材角色`} title={roleGuidance(role)}>{ROLE_OPTIONS.map((option) => <button key={option.value} type="button" aria-pressed={role === option.value} onClick={() => role !== option.value && onSetRole(option.value)}>{option.label}</button>)}</div>
    <div className="library-book-actions"><button onClick={onReindex} disabled={reindexing} className="app-secondary-button"><RefreshCw className={`h-4 w-4 ${reindexing ? 'animate-spin' : ''}`} />{reindexing ? '重建中' : '重索引'}</button>{!active ? <button onClick={onSwitch} className="app-ghost-button">设为当前</button> : <span className="library-active-label">当前教材</span>}<BookOverflowMenu onRename={onRename} onArchive={onArchive} /></div>
  </article>;
}

function ArchivedBookList({ books, onRestore }: { books: LibraryBook[]; onRestore: (reference: string) => void }) {
  if (!books.length) return <div className="library-empty"><Archive className="h-5 w-5" /><strong>没有已归档教材</strong></div>;
  return <div className="library-archive-list">{books.map((book) => <div key={book.book_id || book.name} className="library-archive-row"><div><strong>{book.display_name || book.name}</strong><span>{book.has_pdf ? 'PDF' : 'OCR / Markdown'} · {book.chapter_count || 0} 章</span></div><button onClick={() => onRestore(book.book_id || book.name)} className="app-secondary-button">恢复</button></div>)}</div>;
}

function BookOverflowMenu({ onRename, onArchive }: { onRename: () => void; onArchive: () => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const pointer = (event: PointerEvent) => { if (!rootRef.current?.contains(event.target as Node)) setOpen(false); };
    const keyboard = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); triggerRef.current?.focus(); } };
    document.addEventListener('pointerdown', pointer, true); document.addEventListener('keydown', keyboard);
    return () => { document.removeEventListener('pointerdown', pointer, true); document.removeEventListener('keydown', keyboard); };
  }, [open]);
  return <div ref={rootRef} className="library-overflow"><button ref={triggerRef} type="button" onClick={() => setOpen((value) => !value)} className="app-icon-button" aria-label="更多教材操作" aria-expanded={open} aria-haspopup="menu"><MoreHorizontal className="h-4 w-4" /></button>{open && <div className="library-overflow-menu" role="menu"><button type="button" role="menuitem" onClick={() => { setOpen(false); onRename(); }}><Pencil className="h-3.5 w-3.5" />重命名</button><button type="button" role="menuitem" onClick={() => { setOpen(false); onArchive(); }} className="is-danger"><Archive className="h-3.5 w-3.5" />归档教材</button></div>}</div>;
}
