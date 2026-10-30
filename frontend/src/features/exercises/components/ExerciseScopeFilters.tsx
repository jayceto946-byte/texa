import ScopeSelector from '../../../components/ScopeSelector';
import { SegmentedControl } from '../../../components/ui/SelectionControls';
import type { BookInfo } from '../../../types';
import { ChevronDown } from 'lucide-react';

import { exerciseSubjectMatches } from '../exerciseSource';

export function ExerciseScopeFilters({ subject, bookName, books, chapter, chapters, practiceState, onSubject, onBook, onChapter, onPracticeState }: {
  subject: string; bookName: string; books: BookInfo[]; chapter: string; chapters: string[]; practiceState: string;
  onSubject: (value: string) => void; onBook: (value: string) => void; onChapter: (value: string) => void; onPracticeState: (value: string) => void;
}) {
  const scopedBooks = books.filter(book => exerciseSubjectMatches(book.subject || '', subject));
  return <section className="exercise-scope-filters" aria-label="题目范围">
    <div className="exercise-scope-levels">
      <div className="exercise-scope-field"><span>学科</span><ScopeSelector size="form" label="筛选学科" subject={subject} books={books} bookMode="hidden" onSubjectChange={onSubject} fullWidth /></div>
      <label className="exercise-scope-field"><span>教材</span><select aria-label="筛选教材" value={bookName === 'default' ? '' : bookName} onChange={event => onBook(event.target.value)}>
        <option value="">独立题库</option>{scopedBooks.map(book => <option key={book.book_id || book.name} value={book.name}>{book.displayName || book.name}</option>)}
      </select><ChevronDown className="exercise-scope-chevron" size={16} aria-hidden="true" /></label>
      <label className="exercise-scope-field"><span>章节</span><select aria-label="筛选章节" value={chapter} onChange={event => onChapter(event.target.value)} disabled={!chapters.length}>
        <option value="">全部章节</option>{chapters.map(title => <option key={title} value={title}>{title}</option>)}
      </select><ChevronDown className="exercise-scope-chevron" size={16} aria-hidden="true" /></label>
    </div>
    <div className="exercise-practice-filter"><span>练习记录</span><SegmentedControl label="练习记录筛选" value={practiceState} options={[{ value: '', label: '全部' }, { value: 'unpracticed', label: '未练习' }, { value: 'practiced', label: '练习过' }]} onChange={onPracticeState} /></div>
  </section>;
}
