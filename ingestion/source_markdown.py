"""Readable source tables without changing their stored OCR or numeric content."""
from html.parser import HTMLParser
import re


def _cell_markdown(value):
    value = str(value).strip().replace('\n', ' ')
    if value.startswith('$') and not value.startswith('$$') and value.endswith('$'):
        value = re.sub(r'(?<!\$)\$\$(?!\$)', '$ $', value)
    else:
        value = re.sub(r'\$\$(.+?)\$\$', lambda m: '$'+m[1]+'$', value)
    def math_cell(match):
        return '$'+re.sub(r'(?<!\\)\|', r'\\vert ', match[1])+'$'
    value = re.sub(r'(?<!\\)\$([^$]+)\$', math_cell, value)
    return re.sub(r'(?<!\\)\|', r'\\|', value)


class _TableGrid(HTMLParser):
    def __init__(self):
        super().__init__()
        self.grid, self.cell = {}, None
        self.row = -1

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row += 1; self.column = 0
        elif tag in {'td','th'} and self.row >= 0:
            attrs = dict(attrs)
            self.cell = []
            self.span = (int(attrs.get('rowspan','1')),int(attrs.get('colspan','1')))
        elif tag == 'br' and self.cell is not None:
            self.cell.append(' ')
        elif tag == 'img' and self.cell is not None:
            self.cell.append(self.get_starttag_text())

    def handle_data(self, data):
        if self.cell is not None:self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {'td','th'} and self.cell is not None:
            while (self.row,self.column) in self.grid:self.column += 1
            text = ''.join(self.cell).strip()
            for row in range(self.row,self.row+self.span[0]):
                for column in range(self.column,self.column+self.span[1]):
                    self.grid[row,column] = text
            self.column += self.span[1]; self.cell = None


def table_markdown(text):
    def html_table(match):
        parser = _TableGrid(); parser.feed(match[0]); parser.close()
        if not parser.grid:return match[0]
        height = max(r for r,c in parser.grid)+1; width = max(c for r,c in parser.grid)+1
        rows = [[parser.grid.get((r,c),'') for c in range(width)] for r in range(height)]
        rows.insert(1,['---']*width)
        return '\n'.join('| '+' | '.join(_cell_markdown(cell) for cell in row)+' |' for row in rows)
    text = re.sub(r'<table\b[^>]*>[\s\S]*?</table>',html_table,text,flags=re.I)
    lines = []
    for line in text.splitlines():
        if line.strip().startswith('|'):
            # Source table delimiters stay in place; only normalize each cell.
            cells = re.split(r'(?<!\\)\|',line.strip().strip('|'))
            line = '| '+' | '.join(_cell_markdown(cell) for cell in cells)+' |'
        lines.append(line)
    return '\n'.join(lines)
