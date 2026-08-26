export type TextbookRecord = {
  name: string;
  subject?: string;
  displayName?: string;
  book_role?: 'standalone' | 'core' | 'reference';
  resource_group?: string;
};

export type TextbookScopeOption = {
  name: string;
  subject?: string;
  displayName?: string;
  sourceNames?: string[];
};

function clean(value = '') {
  return value.trim().replace(/^\/+|\/+$/g, '');
}

function subjectParts(value = '') {
  return clean(value).split('/').map(clean).filter(Boolean);
}

export function formatLearningScopeLabel(subject = '', scopeLabel = '') {
  const parts = subjectParts(subject);
  const normalizedScope = clean(scopeLabel);
  const subjectLabel = parts.length ? parts.join(' / ') : '未限定学科';
  if (!normalizedScope || normalizedScope === parts.at(-1)) return subjectLabel;
  return `${subjectLabel} · ${normalizedScope}`;
}

function groupKey(book: TextbookRecord) {
  if (book.book_role !== 'core' && book.book_role !== 'reference') return '';
  const group = clean(book.resource_group || '') || clean(book.subject || '');
  return group ? `group:${group}` : '';
}

function groupLabel(book: TextbookRecord) {
  const explicit = clean(book.resource_group || '');
  if (explicit) return explicit;
  const subject = clean(book.subject || '');
  return subjectParts(subject).at(-1) || book.displayName || book.name;
}

/**
 * Convert physical textbook files into the logical ranges shown in chat.
 * A core book and its reference books share one range when they have the
 * same explicit resource group, or the same subject as a safe default.
 */
export function buildTextbookScopeOptions(books: TextbookRecord[]): TextbookScopeOption[] {
  const grouped = new Map<string, TextbookRecord[]>();
  for (const book of books) {
    const key = groupKey(book);
    if (key) grouped.set(key, [...(grouped.get(key) || []), book]);
  }

  const collapsible = new Set(
    Array.from(grouped.entries())
      .filter(([, members]) => members.length > 1 && members.some((book) => book.book_role === 'core'))
      .map(([key]) => key),
  );
  const emitted = new Set<string>();
  const result: TextbookScopeOption[] = [];

  for (const book of books) {
    const key = groupKey(book);
    if (!key || !collapsible.has(key)) {
      result.push({ name: book.name, subject: book.subject, displayName: book.displayName, sourceNames: [book.name] });
      continue;
    }
    if (emitted.has(key)) continue;
    emitted.add(key);
    const members = grouped.get(key) || [book];
    const primary = members.find((item) => item.book_role === 'core') || members[0];
    result.push({
      name: primary.name,
      subject: primary.subject,
      displayName: groupLabel(primary),
      sourceNames: members.map((item) => item.name),
    });
  }

  return result;
}

export function scopeContainsBook(scope: TextbookScopeOption, bookName: string) {
  return scope.name === bookName || Boolean(scope.sourceNames?.includes(bookName));
}

export function findDefaultTextbookScope(scopes: TextbookScopeOption[], subject: string) {
  const selectedSubject = clean(subject);
  if (!selectedSubject) return undefined;
  return scopes.find((scope) => {
    const bookSubject = clean(scope.subject || '');
    return bookSubject === selectedSubject || bookSubject.startsWith(`${selectedSubject}/`);
  });
}
