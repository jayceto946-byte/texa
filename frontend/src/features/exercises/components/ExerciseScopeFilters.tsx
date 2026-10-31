import Selector from '../../../components/ui/Selector';
import ScopeSelector from '../../../components/ScopeSelector';
import { SegmentedControl } from '../../../components/ui/SelectionControls';
import type { BookInfo } from '../../../types';

import { exerciseSubjectMatches } from '../exerciseSource';

export function ExerciseScopeFilters({ subject, bookName, books, chapter, chapters, practiceState, onSubject, onBook, onChapter, onPracticeState }: {
  subject: string; bookName: string; books: BookInfo[]; chapter: string; chapters: string[]; practiceState: string;
  onSubject: (value: string) => void; onBook: (value: string) => void; onChapter: (value: string) => void; onPracticeState: (value: string) => void;
}) {
  const scopedBooks = books.filter(book => exerciseSubjectMatches(book.subject || '', subject));
  return <section className="exercise-scope-filters" aria-label="题目范围">
    <div className="exercise-scope-levels">
      <div className="exercise-scope-field"><span>学科</span><ScopeSelector size="form" label="筛选学科" subject={subject} books={books} bookMode="hidden" onSubjectChange={onSubject} fullWidth /></div>
      <label className="exercise-scope-field"><span>教材</span><Selector ariaLabel="筛选教材" value={bookName === 'default' ? '' : bookName} onChange={value => onBook(value)} options={[{ value: "", label: "独立题库" }, ...scopedBooks.map((book) => ({ value: book.name, label: book.displayName || book.name }))]}/></label>
      <label className="exercise-scope-field"><span>章节</span><Selector ariaLabel="筛选章节" value={chapter} onChange={value => onChapter(value)} options={[{ value: "", label: "全部章节" }, ...chapters.map((title) => ({ value: title, label: title }))]} disabled={!chapters.length}/></label>
    </div>
    <div className="exercise-practice-filter"><span>练习记录</span><SegmentedControl label="练习记录筛选" value={practiceState} options={[{ value: '', label: '全部' }, { value: 'unpracticed', label: '未练习' }, { value: 'practiced', label: '练习过' }]} onChange={onPracticeState} /></div>
  </section>;
}
