/** remark-math treats $$x$$ on one line as inline math. Preserve display intent locally. */
export function readingMathMarkdown(content: string): string {
  return content.replace(/(```[\s\S]*?```|`[^`\n]*`)|\$\$([\s\S]*?)\$\$/g, (match, code: string | undefined, math: string | undefined) => code ? match : `\n\n$$\n${math?.trim() || ''}\n$$\n\n`);
}
