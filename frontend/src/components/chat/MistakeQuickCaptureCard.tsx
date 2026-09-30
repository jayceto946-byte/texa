import { Link } from 'react-router-dom';
import { ImagePlus } from 'lucide-react';

/** Chat and notebook share the same durable capture draft. */
export default function MistakeQuickCaptureCard({ bookName }: { bookName: string; subject: string }) {
  const query = `?book_name=${encodeURIComponent(bookName || 'default')}`;
  return <div className="rounded-xl border border-border bg-[var(--surface-subtle)] p-4">
    <div className="mb-2 flex items-center gap-2 text-base font-semibold text-text-primary"><ImagePlus className="h-4 w-4 text-accent" />补录错题</div>
    <p className="mb-3 text-sm text-text-secondary">图片和手动录入使用同一份可恢复草稿。识别后先校对题目，再决定是否收录。</p>
    <Link className="app-primary-button inline-flex" to={`/mistakes/intake${query}`}>打开补录</Link>
  </div>;
}
