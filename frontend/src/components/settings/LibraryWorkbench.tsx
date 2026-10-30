import { TexaTextbook, TexaEdit, TexaDelete, TexaClose } from '../icons';
import { useCallback, useEffect, useMemo, useState, type MouseEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { AlertTriangle, Archive, CheckCircle2, ChevronDown, ChevronRight, FolderOpen, MoreHorizontal, Plus, RefreshCw } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router-dom';
import ScopeSelector from '../ScopeSelector';
import ContextMenu from '../ui/ContextMenu';
import './LibraryWorkbench.css';
import { EmptyState } from '../ui/AsyncState';
import FigureAuditPanel from '../../features/textbooks/FigureAuditPanel';
import OutlineCalibrationPanel from '../../features/textbooks/OutlineCalibrationPanel';
import ConceptExtractionStatus from '../../features/textbooks/ConceptExtractionStatus';

export type LibrarySubject = { name: string; children: string[] };
export type BookReadiness = {
  technical?: { status?: 'ready' | 'degraded' | 'missing'; vector_ready?: boolean; lexical_ready?: boolean; chunk_count?: number; index_version?: string };
  canonical?: { status?: 'ready' | 'needs_review' | 'invalid' | 'unavailable'; warning_count?: number; error_count?: number; block_count?: number };
  semantic?: { status?: 'verified' | 'unverified'; release_status?: string; case_count?: number; human_case_count?: number; generated_probe_cases?: number };
  retrieval?: { status?: string; case_count?: number; failed_case_count?: number; warnings?: string[]; failed_cases?: { id: string; question: string; missing_points?: string[]; provenance?: { page_start?: number | null; page_end?: number | null } }[] };
};
export type LibraryBook = { name: string; book_id?: string; storage_name?: string; display_name?: string; lifecycle_status?: 'active' | 'archived'; subject?: string; path?: string; has_pdf?: boolean; chapter_count?: number; book_role?: 'standalone' | 'core' | 'reference'; rag_priority?: number; resource_group?: string; readiness?: BookReadiness };

type Props = {
  subjects: LibrarySubject[]; books: LibraryBook[]; selectedSubjectIndex: number; selectedChildIndex: number | null;
  onSelect: (subjectIndex: number, childIndex: number | null) => void; onAddSubject: () => void; onAddChild: (subjectIndex: number) => void;
  onRenameSubject: (index: number, name: string) => void; onRenameChild: (subjectIndex: number, childIndex: number, name: string) => void;
  onDeleteSubject: (index: number) => void; onDeleteChild: (subjectIndex: number, childIndex: number) => void;
  onRefresh: () => void; onMoveBook: (name: string, target: string) => void;
  onSetRole: (name: string, role: 'standalone' | 'core' | 'reference') => void; onSetResourceGroup: (name: string, resourceGroup: string) => void;
  onSwitchBook: (name: string) => void; onDeleteBook: (name: string) => void;
  onRenameBook: (name: string, displayName: string) => void; onReindexBook: (name: string) => void; reindexingBook?: string; currentBookName?: string;
};

type CategoryTarget = { subjectIndex: number; childIndex: number | null; name: string };
type CategoryMenu = CategoryTarget & { x: number; y: number; trigger: HTMLElement };

const subjectPath = (parent = '', child = '') => child ? `${parent}/${child}` : parent;
const belongsTo = (book: LibraryBook, parent: string, child = '') => {
  const value = (book.subject || '').trim();
  if (!parent) return !value;
  if (child) return value === subjectPath(parent, child) || value === child;
  return value === parent || value.startsWith(`${parent}/`);
};

export default function LibraryWorkbench(props: Props) {
  const { subjects, books, selectedSubjectIndex, selectedChildIndex, onSelect } = props;
  const { pathname } = useLocation();
  const [navigationHost, setNavigationHost] = useState<HTMLElement | null>(null);
  useEffect(() => {
    const media = window.matchMedia('(min-width: 920px)');
    const update = () => setNavigationHost(pathname === '/books' && media.matches ? document.getElementById('workspace-context-navigation') : null);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [pathname]);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [listMode, setListMode] = useState<'active' | 'archived'>('active');
  const [renameTarget, setRenameTarget] = useState<CategoryTarget | null>(null);
  const [categoryMenu, setCategoryMenu] = useState<CategoryMenu | null>(null);
  const closeCategoryMenu = useCallback(() => setCategoryMenu(null), []);
  const [renameDraft, setRenameDraft] = useState('');
  const subject = selectedSubjectIndex >= 0 ? subjects[selectedSubjectIndex] || null : null;
  const child = subject && selectedChildIndex !== null ? subject.children[selectedChildIndex] || '' : '';
  const activeBooks = useMemo(() => books.filter((book) => book.lifecycle_status !== 'archived'), [books]);
  const archivedBooks = useMemo(() => books.filter((book) => book.lifecycle_status === 'archived'), [books]);
  const currentBooks = useMemo(() => subject ? activeBooks.filter((book) => belongsTo(book, subject.name, child)) : activeBooks.filter((book) => !(book.subject || '').trim()), [activeBooks, subject, child]);
  const categoryName = child || subject?.name || '未分类教材';

  useEffect(() => { setRenameTarget(null); }, [selectedSubjectIndex, selectedChildIndex]);

  const hasBooks = (target: CategoryTarget) => {
    const parent = subjects[target.subjectIndex];
    return Boolean(parent && books.some(book => belongsTo(book, parent.name, target.childIndex === null ? '' : parent.children[target.childIndex])));
  };

  const select = (subjectIndex: number, childIndex: number | null) => {
    onSelect(subjectIndex, childIndex);
    setListMode('active');
    if (subjectIndex >= 0) setExpanded((value) => ({ ...value, [subjectIndex]: true }));
  };

  const openCategoryMenu = (event: MouseEvent<HTMLElement> | ReactKeyboardEvent<HTMLElement>, target: CategoryTarget) => {
    if ('key' in event && event.key !== 'ContextMenu' && !(event.shiftKey && event.key === 'F10')) return;
    event.preventDefault();
    event.stopPropagation();
    const trigger = event.currentTarget.matches('button') ? event.currentTarget : event.currentTarget.querySelector<HTMLElement>('.library-tree-item');
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    setCategoryMenu({ ...target, trigger, x: 'clientX' in event ? event.clientX : rect.left + 12, y: 'clientY' in event ? event.clientY : rect.bottom });
  };

  const commitCategoryRename = () => {
    const next = renameDraft.trim();
    if (!renameTarget || !next || hasBooks(renameTarget)) return;
    if (renameTarget.childIndex === null) props.onRenameSubject(renameTarget.subjectIndex, next);
    else props.onRenameChild(renameTarget.subjectIndex, renameTarget.childIndex, next);
    setRenameTarget(null);
  };

  const categoryTree = (
        <aside className="library-tree" aria-label="教材分类">
          {renameTarget && <div className="library-inline-rename">
            <input autoFocus value={renameDraft} onChange={event => setRenameDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.nativeEvent.isComposing) commitCategoryRename(); if (event.key === 'Escape') setRenameTarget(null); }} aria-label={`${renameTarget.childIndex === null ? '学科' : '科目'}名称`} />
            <button onClick={commitCategoryRename} className="app-secondary-button">确定</button>
            <button onClick={() => setRenameTarget(null)} className="app-icon-button" aria-label="取消重命名"><TexaClose className="h-4 w-4" /></button>
          </div>}
          <div className="study-classification-tools">
            <button onClick={props.onAddSubject} className="library-category-add"><Plus className="h-4 w-4" />添加学科</button>
            {subject && <button onClick={() => props.onAddChild(selectedSubjectIndex)} className="library-category-add"><Plus className="h-4 w-4" />添加科目</button>}
          </div>
          <div className="library-tree-list">
            {subjects.map((item, index) => {
              const open = expanded[index] ?? selectedSubjectIndex === index;
              const active = selectedSubjectIndex === index && selectedChildIndex === null;
              const count = activeBooks.filter((book) => belongsTo(book, item.name)).length;
              return <div key={`${item.name}-${index}`}>
                <div className={`library-tree-parent ${active ? 'is-active' : ''}`}
                  onContextMenu={event => openCategoryMenu(event, { subjectIndex: index, childIndex: null, name: item.name })}
                  onKeyDown={event => openCategoryMenu(event, { subjectIndex: index, childIndex: null, name: item.name })}>
                  <button onClick={() => setExpanded((value) => ({ ...value, [index]: !open }))} className="library-tree-disclosure" aria-label={open ? '折叠' : '展开'}>{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button>
                  <button onClick={() => select(index, null)} className="library-tree-item" aria-haspopup="menu" aria-expanded={categoryMenu?.subjectIndex === index && categoryMenu.childIndex === null} title="右键管理学科"><FolderOpen className="h-4 w-4" /><span>{item.name}</span><span className="library-tree-count">{count}</span></button>
                </div>
                {open && <div className="library-tree-children">
                  {item.children.map((childName, childIndex) => <button key={`${childName}-${childIndex}`} onClick={() => select(index, childIndex)}
                    onContextMenu={event => openCategoryMenu(event, { subjectIndex: index, childIndex, name: childName })}
                    onKeyDown={event => openCategoryMenu(event, { subjectIndex: index, childIndex, name: childName })}
                    aria-haspopup="menu" aria-expanded={categoryMenu?.subjectIndex === index && categoryMenu.childIndex === childIndex} title="右键管理科目"
                    className={`library-tree-child ${selectedSubjectIndex === index && selectedChildIndex === childIndex ? 'is-active' : ''}`}><span>{childName}</span><span className="library-tree-count">{activeBooks.filter((book) => belongsTo(book, item.name, childName)).length}</span></button>)}
                </div>}
              </div>;
            })}
            <button onClick={() => select(-1, null)} className={`library-tree-uncategorized ${selectedSubjectIndex < 0 ? 'is-active' : ''}`}><Archive className="h-4 w-4" /><span>未分类</span><span className="library-tree-count">{activeBooks.filter((book) => !(book.subject || '').trim()).length}</span></button>
          </div>
        </aside>
  );

  return (
    <section className="library-manager">
      {categoryMenu && <ContextMenu x={categoryMenu.x} y={categoryMenu.y} label={`${categoryMenu.name}管理`} trigger={categoryMenu.trigger} onClose={closeCategoryMenu} items={[
        { label: '重命名', icon: <TexaEdit className="h-3.5 w-3.5" />, disabled: hasBooks(categoryMenu), title: hasBooks(categoryMenu) ? '请先移出该目录中的教材' : undefined,
          onSelect: () => { setRenameDraft(categoryMenu.name); setRenameTarget(categoryMenu); } },
        { label: categoryMenu.childIndex === null ? '删除学科' : '删除科目', icon: <TexaDelete className="h-3.5 w-3.5" />, danger: true, disabled: hasBooks(categoryMenu), title: hasBooks(categoryMenu) ? '请先移出该目录中的教材' : undefined,
          onSelect: () => categoryMenu.childIndex === null ? props.onDeleteSubject(categoryMenu.subjectIndex) : props.onDeleteChild(categoryMenu.subjectIndex, categoryMenu.childIndex) },
      ]} />}

      <div className="library-workbench">
        {navigationHost ? createPortal(categoryTree, navigationHost) : categoryTree}

        <main className="library-content">
          <header className="library-category-header">
            <div className="library-category-identity">
              <div><h3>{categoryName}</h3><p>{currentBooks.length} 本教材</p></div>
            </div>
          </header>
          <div className="library-header-tools library-context-toolbar workspace-collection-toolbar">

              <div className="library-list-filter" role="group" aria-label="教材状态"><button aria-pressed={listMode === 'active'} onClick={() => setListMode('active')}>全部教材 <span>{activeBooks.length}</span></button><button aria-pressed={listMode === 'archived'} onClick={() => setListMode('archived')}>此前归档 <span>{archivedBooks.length}</span></button></div>
              <button onClick={props.onRefresh} className="app-icon-button" title="刷新教材" aria-label="刷新教材"><RefreshCw className="h-4 w-4" /></button>
          </div>

          {listMode === 'active' ? <div className="library-book-list">
            {currentBooks.length > 0 && <div className="library-list-columns" aria-hidden="true"><span>教材</span><span>教材状态</span><span>分类 / 配套教材</span><span>使用方式</span><span>操作</span></div>}
            {currentBooks.map((book) => <BookRow key={book.book_id || book.name} book={book} active={props.currentBookName === book.name} subjects={subjects} reindexing={props.reindexingBook === book.name} onMove={(value) => props.onMoveBook(book.name, value)} onSetRole={(role) => props.onSetRole(book.name, role)} onSetResourceGroup={(group) => props.onSetResourceGroup(book.name, group)} onSwitch={() => props.onSwitchBook(book.name)} onReindex={() => props.onReindexBook(book.name)} onRename={() => props.onRenameBook(book.name, book.display_name || book.name)} onDelete={() => props.onDeleteBook(book.book_id || book.name)} />)}
            {!currentBooks.length && <EmptyState className="library-empty" icon={<TexaTextbook />} title="这里还没有教材" description="移动已有教材到此处，或导入新教材。" />}
          </div> : <ArchivedBookList books={archivedBooks} onDelete={props.onDeleteBook} />}
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
  const retrieval = book.readiness?.retrieval;
  const retrievalNeedsAttention = retrieval?.status === 'warning';
  const contentNeedsAttention = canonical?.status === 'needs_review' || canonical?.status === 'invalid';
  const ready = technicalReady && !contentNeedsAttention && !retrievalNeedsAttention;
  const statusLabel = ready
    ? '可用于学习'
    : technicalReady && retrievalNeedsAttention && canonical?.status !== 'invalid'
      ? '可用于学习，部分内容检索待核对'
    : technical?.status === 'degraded'
      ? '可使用，部分内容可能找不到'
      : contentNeedsAttention
        ? '需要检查教材内容'
        : '尚未准备完成';
  return <div className="library-readiness">
    <span className={ready ? 'is-ready' : 'is-warning'}>{ready ? <CheckCircle2 /> : <AlertTriangle />}<b>{statusLabel}</b></span>
    <details className="type-caption text-text-secondary">
      <summary className="cursor-pointer hover:text-text-primary">详细信息</summary>
      <div className="mt-1 break-words leading-5">
        <div>检索：{technicalReady ? `可用 · ${technical?.chunk_count || 0} 个内容片段` : technical?.status === 'degraded' ? '部分可用' : '未就绪'}</div>
        <div>内容结构：{canonicalReady ? '完整' : canonical?.status === 'needs_review' ? `${canonical.warning_count || 0} 项待检查` : canonical?.status === 'invalid' ? '不可用' : '尚无记录'}</div>
        <div>人工抽查：{book.readiness?.semantic?.status === 'verified' ? `已完成 ${book.readiness.semantic.human_case_count || 0} 例` : '尚未完成'}</div>
        {retrieval?.warnings?.map((warning) => <p key={warning}>{warning}</p>)}
        {retrieval?.failed_cases?.map((item) => <div key={item.id}>
          <p>{item.provenance?.page_start != null ? `第 ${item.provenance.page_start} 页 · ` : ''}{item.question}</p>
          {!!item.missing_points?.length && <details>
            <summary className="cursor-pointer">未召回片段（{item.missing_points.length} 项）</summary>
            <p>{item.missing_points.join('、')}</p>
          </details>}
        </div>)}
      </div>
    </details>
  </div>;
}

function BookRow({ book, active, subjects, reindexing, onMove, onSetRole, onSetResourceGroup, onSwitch, onReindex, onRename, onDelete }: { book: LibraryBook; active: boolean; subjects: LibrarySubject[]; reindexing: boolean; onMove: (target: string) => void; onSetRole: (role: 'standalone' | 'core' | 'reference') => void; onSetResourceGroup: (group: string) => void; onSwitch: () => void; onReindex: () => void; onRename: () => void; onDelete: () => void }) {
  const role = book.book_role || 'standalone';
  const [auditOpen, setAuditOpen] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(false);
  return <article className={`library-book-row workspace-register-row${active ? ' is-current' : ''}`}>
    <div className="library-book-identity"><TexaTextbook className="study-book-icon" aria-hidden="true" /><div><h4>{book.display_name || book.name}</h4>{active && <span className="library-current-status">学习中</span>}</div><p>{book.has_pdf ? 'PDF' : '已解析教材'} · {book.chapter_count || 0} 章</p><button type="button" className="app-ghost-button outline-calibration-trigger" aria-expanded={outlineOpen} onClick={() => setOutlineOpen(value => !value)}>目录不符？校准</button></div>
    <div><ReadinessSummary book={book} /><ConceptExtractionStatus bookName={book.storage_name || book.name} /></div>
    <div className="library-book-scope">
      <div className="library-subject-field"><span>归属</span><ScopeSelector size="compact" popupSize="compact" subject={book.subject || ''} subjectTree={subjects} onSubjectChange={onMove} bookMode="hidden" width="normal" label={`${book.display_name || book.name}教材归属`} placeholder="未分类" className="library-subject-selector" /></div>
      {role === 'standalone' ? <div className="library-resource-group-static"><span>配套</span><strong>单独使用</strong></div> : <label><span>配套</span><input aria-label={`${book.display_name || book.name}配套教材组`} defaultValue={book.resource_group || ''} placeholder={book.subject ? `默认：${book.subject}` : '输入组名'} onBlur={(event) => onSetResourceGroup(event.target.value.trim())} /></label>}
    </div>
    <select className="study-role-select" value={role} aria-label={`${book.display_name || book.name}的教材角色`} title={roleGuidance(role)} onChange={(event) => onSetRole(event.target.value as typeof role)}>{ROLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
    <div className="library-book-actions"><button onClick={onReindex} disabled={reindexing} className="app-secondary-button"><RefreshCw className={`h-4 w-4 ${reindexing ? 'animate-spin' : ''}`} />{reindexing ? '准备中' : '重新准备'}</button>{!active ? <button onClick={onSwitch} className="app-ghost-button">设为学习范围</button> : <span className="library-active-label">当前学习范围</span>}<BookOverflowMenu onRename={onRename} onDelete={onDelete} onAudit={() => setAuditOpen(true)} /></div>
    {auditOpen && <FigureAuditPanel bookName={book.storage_name || book.name} onClose={() => setAuditOpen(false)} />}
    {outlineOpen && <OutlineCalibrationPanel bookName={book.storage_name || book.name} onClose={() => setOutlineOpen(false)} />}
  </article>;
}

function ArchivedBookList({ books, onDelete }: { books: LibraryBook[]; onDelete: (reference: string) => void }) {
  if (!books.length) return <EmptyState className="library-empty" icon={<Archive />} title="没有已归档教材" />;
  return <div className="library-archive-list">{books.map((book) => <div key={book.book_id || book.name} className="library-archive-row"><div><strong>{book.display_name || book.name}</strong><span>{book.has_pdf ? 'PDF' : 'OCR / Markdown'} · {book.chapter_count || 0} 章</span></div><button onClick={() => onDelete(book.book_id || book.name)} className="app-secondary-button">删除教材</button></div>)}</div>;
}

function BookOverflowMenu({ onRename, onDelete, onAudit }: { onRename: () => void; onDelete: () => void; onAudit: () => void }) {
  const [menu, setMenu] = useState<{ x: number; y: number; trigger: HTMLElement } | null>(null);
  return <><button type="button" className="app-icon-button" aria-label="更多教材操作" aria-expanded={!!menu} aria-haspopup="menu" onClick={event => {
    const rect = event.currentTarget.getBoundingClientRect();
    setMenu({ x: rect.right - 184, y: rect.bottom + 4, trigger: event.currentTarget });
  }}><MoreHorizontal className="h-4 w-4" /></button>{menu && <ContextMenu {...menu} label="教材操作" onClose={() => setMenu(null)} items={[
    { label: '审核图片', icon: <CheckCircle2 className="h-3.5 w-3.5" />, onSelect: onAudit },
    { label: '重命名', icon: <TexaEdit className="h-3.5 w-3.5" />, onSelect: onRename },
    { label: '删除教材', icon: <TexaDelete className="h-3.5 w-3.5" />, danger: true, onSelect: onDelete },
  ]} />}</>;
}
