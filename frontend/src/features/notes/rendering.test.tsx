import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MarkdownMessage } from '../../components/chat/MarkdownRenderer';
import { SourceGroupList } from '../../components/chat/SourceGroupList';
import { groupSourcesByLocation } from '../../utils/citations';
function render(content: string) {
    return renderToStaticMarkup(<MarkdownMessage disableRemoteMedia content={content} linkedConcepts={[]} onConceptClick={() => { }}/>);
}
describe('Notes reuse the safe reading renderer', () => {
    it('renders matrices and GFM tables without executing HTML or loading remote images', () => {
        const html = render('$$A=\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}$$\n\n|条件|结论|\n|---|---|\n|可导|连续|\n\n<script>alert(1)</script>\n\n![tracking](https://example.com/track)');
        expect(html).toContain('katex');
        expect(html).toContain('<table');
        expect(html).not.toContain('<script>');
        expect(html).not.toContain('<img');
        expect(html).not.toContain('https://example.com/track');
    });
    it('removes unsafe links and disk paths from actionable markup', () => {
        const html = render('[run](javascript:alert(1)) [file](file:///private/secret) [api](/api/actions)');
        expect(html).not.toContain('href="javascript:');
        expect(html).not.toContain('href="file:');
        expect(html).not.toContain('href="/api/actions');
    });
    it('keeps separate source locations for distinct frozen evidence IDs', () => {
        const groups = groupSourcesByLocation([{ id: 'evidence-a', book_name: '数学', chapter: '第一章', section_path: ['第一章', '连续'], page_idx: 2 }, { id: 'evidence-b', book_name: '数学', chapter: '第二章', section_path: ['第二章', '导数'], page_idx: 8 }]);
        const html = renderToStaticMarkup(<SourceGroupList groups={groups} cited={false}/>);
        expect(html).toContain('连续');
        expect(html).toContain('导数');
        expect(html).toContain('p.3');
        expect(html).toContain('p.9');
    });
});
