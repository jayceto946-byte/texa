import { SimpleMarkdown } from '../../components/chat/MarkdownRenderer';
import './reading-markdown.css';
import { readingMathMarkdown } from './readingMath';
/** Same production Markdown/KaTeX pipeline, with explicit display delimiters on their own lines. */
export function ReadingMarkdown({ content }: { content: string }) {
  return <SimpleMarkdown className="reading-markdown" content={readingMathMarkdown(content)}/>;
}
