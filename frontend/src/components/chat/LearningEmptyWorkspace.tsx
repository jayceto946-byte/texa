import { scopeContainsBook, type TextbookScopeOption } from '../../utils/textbookScopes';

export default function LearningEmptyWorkspace({
  bookName,
  subject,
  books,
  isLoading,
}: {
  bookName: string;
  subject: string;
  books: TextbookScopeOption[];
  isLoading: boolean;
}) {
  const currentScope = books.find((book) => scopeContainsBook(book, bookName));
  const textbook = currentScope?.displayName || currentScope?.name || bookName || '通用问答';

  return (
    <section className="learning-empty-workspace" aria-label="开始学习会话">
      <div className="learning-empty-context">
        <span>{subject || '未限定学科'}</span>
        <span aria-hidden="true">/</span>
        <span>{textbook}</span>
      </div>
      <h2>Ask Texa</h2>
      <p>{isLoading ? '正在准备当前学习范围' : '输入问题、公式或上传图片'}</p>
    </section>
  );
}
