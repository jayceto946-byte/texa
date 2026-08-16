import { useEffect, useMemo, useRef, useState } from 'react';
import { Archive, BookOpen, ChevronDown, ChevronRight, FolderOpen, Library, MoreHorizontal, Pencil, Plus, RefreshCw, Save, Trash2 } from 'lucide-react';

export type LibrarySubject = { name: string; children: string[] };
export type LibraryBook = { name: string; book_id?: string; storage_name?: string; display_name?: string; lifecycle_status?: 'active' | 'archived'; subject?: string; path?: string; has_pdf?: boolean; chapter_count?: number; book_role?: 'standalone' | 'core' | 'reference'; rag_priority?: number; resource_group?: string };

type Props = {
  subjects: LibrarySubject[]; books: LibraryBook[]; selectedSubjectIndex: number; selectedChildIndex: number | null;
  onSelect: (subjectIndex: number, childIndex: number | null) => void; onAddSubject: () => void; onAddChild: (subjectIndex: number) => void;
  onRenameSubject: (index: number, name: string) => void; onRenameChild: (index: number, name: string) => void;
  onDeleteSubject: (index: number) => void; onDeleteChild: (index: number) => void; onSaveSubjects: () => void;
  onImportBook: () => void; onRefresh: () => void; onMoveBook: (name: string, target: string) => void;
  onSetRole: (name: string, role: 'standalone' | 'core' | 'reference') => void;
  onSetResourceGroup: (name: string, resourceGroup: string) => void;
  onSwitchBook: (name: string) => void; onArchiveBook: (name: string) => void;
  onRestoreBook: (name: string) => void; onRenameBook: (name: string, displayName: string) => void;
  currentBookName?: string;
};

const pathFor = (parent = '', child = '') => child ? `${parent}/${child}` : parent;
const belongsTo = (book: LibraryBook, parent: string, child = '') => {
  const value = (book.subject || '').trim();
  if (!parent) return !value;
  if (child) return value === pathFor(parent, child) || value === child;
  return value === parent || value.startsWith(`${parent}/`);
};

export default function LibraryManager(props: Props) {
  const { subjects, books, selectedSubjectIndex, selectedChildIndex, onSelect } = props;
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const subject = selectedSubjectIndex >= 0 ? subjects[selectedSubjectIndex] || null : null;
  const child = subject && selectedChildIndex !== null ? subject.children[selectedChildIndex] || '' : '';
  const target = subject ? pathFor(subject.name, child) : '';
  const activeBooks = useMemo(() => books.filter((book) => book.lifecycle_status !== 'archived'), [books]);
  const archivedBooks = useMemo(() => books.filter((book) => book.lifecycle_status === 'archived'), [books]);
  const currentBooks = useMemo(() => subject ? activeBooks.filter((book) => belongsTo(book, subject.name, child)) : activeBooks.filter((book) => !(book.subject || '').trim()), [activeBooks, subject, child]);
  const parentHasBooks = subject ? activeBooks.some((book) => belongsTo(book, subject.name)) : false;
  const selectedHasBooks = subject && child ? activeBooks.some((book) => belongsTo(book, subject.name, child)) : parentHasBooks;

  const select = (subjectIndex: number, childIndex: number | null) => {
    onSelect(subjectIndex, childIndex);
    if (subjectIndex >= 0) setExpanded((value) => ({ ...value, [subjectIndex]: true }));
  };

  return <section className="space-y-3">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="type-section-title text-text-primary">教材与分类</h2><p className="mt-1 text-xs text-text-secondary">分类调整不会移动教材文件或索引。</p></div>
      <div className="flex gap-2">
        <button onClick={props.onImportBook} className="app-secondary-button"><BookOpen className="h-4 w-4" />导入教材</button>
        <button onClick={props.onSaveSubjects} className="app-primary-button"><Save className="h-4 w-4" />保存目录</button>
      </div>
    </header>

    <div className="grid min-h-[520px] overflow-hidden border-y border-border bg-bg-card lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="border-b border-border bg-bg-secondary/55 p-3 lg:border-b-0 lg:border-r">
        <div className="mb-3 flex items-center justify-between px-1"><span className="flex items-center gap-2 text-sm font-semibold"><Library className="h-4 w-4 text-accent" />学习资料</span><button onClick={props.onAddSubject} className="flex h-8 w-8 items-center justify-center rounded-lg text-text-secondary hover:bg-bg-card hover:text-accent" title="添加一级学科"><Plus className="h-4 w-4" /></button></div>
        <div className="space-y-1">
          {subjects.map((item, index) => {
            const open = expanded[index] ?? selectedSubjectIndex === index;
            const active = selectedSubjectIndex === index && selectedChildIndex === null;
            const count = activeBooks.filter((book) => belongsTo(book, item.name)).length;
            return <div key={`${item.name}-${index}`}>
              <div className={`flex items-center rounded-lg ${active ? 'bg-[var(--accent-soft)] text-accent' : 'hover:bg-bg-card'}`}>
                <button onClick={() => setExpanded((value) => ({ ...value, [index]: !open }))} className="flex h-9 w-8 items-center justify-center text-text-secondary" aria-label={open ? '折叠' : '展开'}>{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button>
                <button onClick={() => select(index, null)} className="flex min-w-0 flex-1 items-center gap-2 py-2 pr-2 text-left text-sm font-medium"><FolderOpen className="h-4 w-4" /><span className="truncate">{item.name}</span><span className="ml-auto text-[11px] text-text-secondary">{count}</span></button>
              </div>
              {open && <div className="ml-5 mt-1 space-y-1 border-l border-border pl-2">
                {item.children.map((childName, childIndex) => <button key={`${childName}-${childIndex}`} onClick={() => select(index, childIndex)} className={`flex w-full items-center rounded-lg px-3 py-2 text-left text-sm ${selectedSubjectIndex === index && selectedChildIndex === childIndex ? 'bg-[var(--accent-soft)] text-accent' : 'text-text-secondary hover:bg-bg-card hover:text-text-primary'}`}><span className="min-w-0 flex-1 truncate">{childName}</span><span className="text-[11px]">{activeBooks.filter((book) => belongsTo(book, item.name, childName)).length}</span></button>)}
                <button onClick={() => { select(index, null); props.onAddChild(index); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-text-secondary hover:bg-bg-card hover:text-accent"><Plus className="h-3.5 w-3.5" />添加科目</button>
              </div>}
            </div>;
          })}
          <button onClick={() => select(-1, null)} className={`mt-2 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${selectedSubjectIndex < 0 ? 'bg-[var(--accent-soft)] text-accent' : 'text-text-secondary hover:bg-bg-card hover:text-text-primary'}`}><Archive className="h-4 w-4" /><span className="flex-1">未分类</span><span className="text-[11px]">{activeBooks.filter((book) => !(book.subject || '').trim()).length}</span></button>
        </div>
      </aside>

      <main className="min-w-0 p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
          <div><div className="text-xs text-text-secondary">{subject ? subject.name : '资料库'}</div><h3 className="mt-1 text-lg font-semibold">{child || subject?.name || '未分类教材'}</h3><div className="mt-1 text-xs text-text-secondary">{currentBooks.length} 本教材{target ? ` · ${target}` : ''}</div></div>
          <button onClick={props.onRefresh} className="app-secondary-button h-9 min-h-9 px-3 text-xs"><RefreshCw className="h-3.5 w-3.5" />刷新</button>
        </div>

        {subject && <div className="mt-4 border-b border-border pb-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[220px] flex-1 text-xs font-medium text-text-secondary">{child ? '科目名称' : '学科名称'}<input value={child || subject.name} disabled={selectedHasBooks} onChange={(event) => selectedChildIndex === null ? props.onRenameSubject(selectedSubjectIndex, event.target.value) : props.onRenameChild(selectedChildIndex, event.target.value)} className="mt-1.5 w-full rounded-lg border border-border bg-bg-card px-3 py-2 text-sm text-text-primary disabled:cursor-not-allowed disabled:bg-bg-primary disabled:text-text-secondary" /></label>
            <button disabled={selectedHasBooks} onClick={() => selectedChildIndex === null ? props.onDeleteSubject(selectedSubjectIndex) : props.onDeleteChild(selectedChildIndex)} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--danger-border)] px-3 py-2 text-xs text-[var(--danger)] disabled:cursor-not-allowed disabled:opacity-40"><Trash2 className="h-3.5 w-3.5" />删除分类</button>
          </div>
          {selectedHasBooks && <p className="mt-2 text-xs text-text-secondary">该分类仍有教材。为保护现有归属，移动教材后才能重命名或删除。</p>}
        </div>}

        <div className="mt-4 space-y-2">
          {currentBooks.map((book) => <BookRow key={book.book_id || book.name} book={book} active={props.currentBookName === book.name} subjects={subjects} onMove={(targetValue) => props.onMoveBook(book.name, targetValue)} onSetRole={(role) => props.onSetRole(book.name, role)} onSetResourceGroup={(group) => props.onSetResourceGroup(book.name, group)} onSwitch={() => props.onSwitchBook(book.name)} onRename={() => props.onRenameBook(book.name, book.display_name || book.name)} onArchive={() => props.onArchiveBook(book.name)} />)}
          {!currentBooks.length && <div className="px-4 py-10 text-center"><BookOpen className="mx-auto h-5 w-5 text-text-secondary" /><div className="mt-2 text-sm font-medium">这里还没有教材</div><div className="mt-1 text-xs text-text-secondary">可以从其他分类移动教材，或导入新教材。</div></div>}
        </div>

        {!!archivedBooks.length && <section className="mt-6 border-t border-border pt-4">
          <h4 className="text-sm font-semibold">已归档教材</h4>
          <p className="mt-1 text-xs text-text-secondary">归档只隐藏入口；恢复不会重建或移动任何数据。</p>
          <div className="mt-3 space-y-2">
            {archivedBooks.map((book) => <div key={book.book_id || book.name} className="flex items-center gap-3 border-b border-border px-1 py-2.5 last:border-b-0"><div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{book.display_name || book.name}</div><div className="mt-0.5 truncate text-[11px] text-text-secondary">存储名：{book.storage_name || book.name}</div></div><button onClick={() => props.onRestoreBook(book.book_id || book.name)} className="rounded-lg border border-border px-2.5 py-1.5 text-xs hover:border-accent">恢复</button></div>)}
          </div>
        </section>}
      </main>
    </div>
  </section>;
}

function roleGuidance(book: LibraryBook) {
  if (book.book_role === 'reference') {
    return '辅助教材：用于补充、交叉验证和缺失内容；仍可正常召回。';
  }
  if (book.book_role === 'core') {
    return '主要教材：回答时优先参考；同组辅助教材用于补充缺失内容。';
  }
  return '独立教材：单独参与检索，不与其他教材组成资料组。';
}

function resourceGroupPlaceholder(book: LibraryBook) {
  return book.subject ? `默认使用归属：${book.subject}` : '同组教材填写相同名称';
}

const ROLE_OPTIONS = [
  { value: 'core' as const, label: '主要' },
  { value: 'reference' as const, label: '辅助' },
  { value: 'standalone' as const, label: '独立' },
];

function BookRow({ book, active, subjects, onMove, onSetRole, onSetResourceGroup, onSwitch, onRename, onArchive }: { book: LibraryBook; active: boolean; subjects: LibrarySubject[]; onMove: (target: string) => void; onSetRole: (role: 'standalone' | 'core' | 'reference') => void; onSetResourceGroup: (group: string) => void; onSwitch: () => void; onRename: () => void; onArchive: () => void }) {
  const role = book.book_role || 'standalone';
  return (
    <article className="grid gap-4 border-b border-border px-1 py-4 last:border-b-0 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <BookOpen className="h-4 w-4 flex-shrink-0 text-accent" />
          <h4 className="min-w-0 truncate text-sm font-semibold text-text-primary">{book.display_name || book.name}</h4>
          {active && <span className="flex-shrink-0 rounded border border-accent/30 px-1.5 py-0.5 text-xs text-accent">当前</span>}
        </div>
        <p className="mt-1 pl-6 text-xs text-text-secondary">
          {book.has_pdf ? 'PDF' : 'OCR/Markdown'} · {book.chapter_count || 0} 章
          {book.display_name && book.display_name !== book.name ? ` · 存储名 ${book.name}` : ''}
        </p>
        <div className="mt-3 pl-6">
          <div className="text-xs font-medium text-text-secondary">回答中的教材角色</div>
          <div className="mt-1.5 inline-flex rounded-lg border border-border bg-bg-card p-0.5" role="group" aria-label={`${book.display_name || book.name}的教材角色`}>
            {ROLE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={role === option.value}
                onClick={() => role !== option.value && onSetRole(option.value)}
                className={`h-8 rounded px-3 text-xs font-medium ${role === option.value ? 'bg-[var(--accent-soft)] text-accent' : 'text-text-secondary hover:bg-bg-secondary hover:text-text-primary'}`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <p className="mt-2 max-w-xl text-xs leading-5 text-text-secondary">{roleGuidance({ ...book, book_role: role })}</p>
        </div>
      </div>
      <div className="flex min-w-0 flex-col justify-between gap-4">
        <div className={`grid gap-3 ${role === 'standalone' ? 'grid-cols-1' : 'sm:grid-cols-2'}`}>
          <label className="text-xs font-medium text-text-secondary">
            归属
            <select
              value={book.subject || ''}
              onChange={(event) => { if (event.target.value !== (book.subject || '')) onMove(event.target.value); }}
              className="mt-1.5 block h-9 w-full rounded-lg border border-border bg-bg-card pl-2.5 pr-8 text-sm text-text-primary outline-none focus:border-accent"
            >
              <option value="">未分类</option>
              {subjects.map((subject) => (
                <optgroup key={subject.name} label={subject.name}>
                  <option value={subject.name}>{subject.name}（未细分）</option>
                  {subject.children.map((child) => (
                    <option key={child} value={subject.name + '/' + child}>{subject.name} / {child}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          {role !== 'standalone' && (
            <label className="text-xs font-medium text-text-secondary">
              资料组
              <input
                defaultValue={book.resource_group || ''}
                placeholder={resourceGroupPlaceholder(book)}
                onBlur={(event) => onSetResourceGroup(event.target.value.trim())}
                className="mt-1.5 block h-9 w-full rounded-lg border border-border bg-bg-card px-2.5 text-sm text-text-primary outline-none focus:border-accent"
              />
            </label>
          )}
        </div>
        <div className="flex items-center justify-end gap-2">
          <button onClick={onSwitch} disabled={active} className="app-secondary-button h-9 min-h-9 px-3 text-xs disabled:cursor-default disabled:opacity-55">{active ? '当前教材' : '用于问答'}</button>
          <BookOverflowMenu onRename={onRename} onArchive={onArchive} />
        </div>
      </div>
    </article>
  );
}

function BookOverflowMenu({ onRename, onArchive }: { onRename: () => void; onArchive: () => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button type="button" onClick={() => setOpen((value) => !value)} className="app-icon-button h-9 w-9" aria-label="更多教材操作" aria-expanded={open} aria-haspopup="menu">
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open && (
        <div className="app-popover-enter absolute bottom-10 right-0 z-30 w-36 rounded-lg border border-border bg-bg-card p-1 shadow-md" role="menu">
          <button type="button" role="menuitem" onClick={() => { setOpen(false); onRename(); }} className="flex h-9 w-full items-center gap-2 rounded px-2.5 text-left text-xs text-text-primary hover:bg-bg-secondary">
            <Pencil className="h-3.5 w-3.5" />重命名
          </button>
          <button type="button" role="menuitem" onClick={() => { setOpen(false); onArchive(); }} className="flex h-9 w-full items-center gap-2 rounded px-2.5 text-left text-xs text-[var(--danger)] hover:bg-[var(--danger-bg)]">
            <Archive className="h-3.5 w-3.5" />隐藏教材
          </button>
        </div>
      )}
    </div>
  );
}
