"""DOCX source reader: preserve OMML structure, table cells and embedded images."""
from pathlib import Path, PurePosixPath
import posixpath
from xml.etree import ElementTree as ET

from ingestion.document_ir import CanonicalBook, DocumentBlock

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def local(node):
    return node.tag.rsplit('}',1)[-1]


def math_text(node):
    """Convert supported OMML nodes; never flatten an unsupported math object."""
    tag=local(node)
    def child(name):
        element=node.find(M+name)
        return math_text(element) if element is not None else ''
    def prop(name,default=''):
        element=node.find('./'+M+tag+'Pr/'+M+name)
        return element.get(M+'val',default) if element is not None else default
    if tag.endswith('Pr') or tag in {'ctrlPr','argPr'}:return ''
    if tag=='t':
        symbols={'∑':r'\sum ','∫':r'\int ','∞':r'\infty ','≤':r'\le ','≥':r'\ge ','≠':r'\ne ','×':r'\times ','÷':r'\div ','α':r'\alpha ','β':r'\beta ','π':r'\pi ','θ':r'\theta ','→':r'\to ','−':'-','{':r'\{','}':r'\}'}
        return ''.join(symbols.get(c,c) for c in node.text or '')
    if tag=='f':
        if prop('type')=='noBar':return r'\binom{'+child('num')+'}{'+child('den')+'}'
        return r'\frac{'+child('num')+'}{'+child('den')+'}'
    if tag in {'sSub','sSup','sSubSup','sPre'}:
        base='{'+child('e')+'}'
        sub='_{'+child('sub')+'}' if node.find(M+'sub') is not None else ''
        sup='^{'+child('sup')+'}' if node.find(M+'sup') is not None else ''
        return ('{}'+sub+sup+base) if tag=='sPre' else base+sub+sup
    if tag=='rad':
        degree=child('deg')
        return r'\sqrt'+('['+degree+']' if degree else '')+'{'+child('e')+'}'
    if tag=='m':
        rows=[' & '.join(math_text(e) for e in row.findall(M+'e')) for row in node.findall(M+'mr')]
        return r'\begin{matrix}'+r' \\ '.join(rows)+r'\end{matrix}'
    if tag=='eqArr':return r'\begin{aligned}'+r' \\ '.join(math_text(e) for e in node.findall(M+'e'))+r'\end{aligned}'
    if tag=='d':
        delimiters={'{':r'\{','}':r'\}','':' .'}
        opening=prop('begChr','(');closing=prop('endChr',')');sep=prop('sepChr','|')
        return r'\left'+delimiters.get(opening,opening)+' '+sep.join(math_text(e) for e in node.findall(M+'e'))+r'\right'+delimiters.get(closing,closing)
    if tag=='nary':
        symbol=prop('chr','∫');operator={'∑':r'\sum','∏':r'\prod','∫':r'\int','∮':r'\oint','⋃':r'\bigcup','⋂':r'\bigcap'}.get(symbol,symbol)
        return operator+('_{'+child('sub')+'}' if child('sub') else '')+('^{'+child('sup')+'}' if child('sup') else '')+' '+child('e')
    if tag=='func':return r'\operatorname{'+child('fName')+'} '+child('e')
    if tag in {'limLow','limUpp'}:return '{'+child('e')+'}'+('_{' if tag=='limLow' else '^{')+child('lim')+'}'
    if tag=='acc':
        accent={'̂':r'\hat','̄':r'\bar','⃗':r'\vec','̃':r'\tilde','̇':r'\dot','̈':r'\ddot'}.get(prop('chr','̂'))
        if accent is None:raise ValueError('不支持的数学重音')
        return accent+'{'+child('e')+'}'
    if tag=='bar':return (r'\underline' if prop('pos')=='bot' else r'\overline')+'{'+child('e')+'}'
    if tag in {'oMath','oMathPara','r','num','den','sub','sup','e','deg','lim','fName','box'}:
        return ''.join(math_text(c) for c in node)
    raise ValueError('不支持的Word数学结构：'+tag)


def read_docx(archive, *, name, asset_root):
    blocks,warnings=[],[]
    next_id=0
    def add(kind,text,source,**extra):
        nonlocal next_id
        block=DocumentBlock(f'word-{next_id}',kind,text,[name],source_kind='docx',source_file=source,**extra)
        blocks.append(block);next_id+=1;return block
    members=set(archive.namelist())
    names=['word/document.xml']+sorted(n for n in members if n.startswith(('word/header','word/footer')) and n.endswith('.xml'))
    for source in names:
        if source not in members:continue
        root=ET.fromstring(archive.read(source))
        relpath=str(PurePosixPath(source).parent/'_rels'/(PurePosixPath(source).name+'.rels'))
        relations={}
        if relpath in members:
            for rel in ET.fromstring(archive.read(relpath)):
                if rel.get('TargetMode')!='External':
                    target=posixpath.normpath(posixpath.join(posixpath.dirname(source),rel.get('Target','')))
                    if target.startswith('word/'):relations[rel.get('Id')]=target
        def paragraph(para):
            images=[];damaged=[]
            def visit(node):
                tag=local(node)
                if node.tag in {M+'oMath',M+'oMathPara'}:
                    try:return '$'+math_text(node)+'$'
                    except ValueError as exc:
                        damaged.append(ET.tostring(node,encoding='unicode'));warnings.append(str(exc)+'，请补充PDF原页核对')
                        return '[Word公式待识别]'
                if tag in {'drawing','pict','object'}:
                    image_count=len(images)
                    ids=[e.get(R+'embed') or e.get(R+'id') for e in node.iter() if e.get(R+'embed') or e.get(R+'id')]
                    for rid in ids:
                        target=relations.get(rid)
                        if target in members and PurePosixPath(target).suffix.lower() in {'.png','.jpg','.jpeg','.gif','.bmp','.tif','.tiff','.webp'}:
                            rel=PurePosixPath(target)
                            dest=Path(asset_root)/rel;dest.parent.mkdir(parents=True,exist_ok=True)
                            dest.write_bytes(archive.read(target));images.append((str(rel),rid))
                    if not ids or len(images)==image_count:
                        damaged.append(ET.tostring(node,encoding='unicode'));warnings.append('Word对象或图片无法读取，请补充PDF原页核对')
                        return '[Word对象待识别]'
                    return ''
                if tag=='t':return node.text or ''
                if node.tag==W+'r':
                    text=''.join(visit(c) for c in node)
                    alignment=node.find('./'+W+'rPr/'+W+'vertAlign')
                    value=alignment.get(W+'val') if alignment is not None else ''
                    if value in {'superscript','subscript'}:
                        return '${}'+('^' if value=='superscript' else '_')+'{'+text+'}$'
                    return text
                if tag=='tab':return '\t'
                if tag in {'br','cr'}:return '\n'
                if tag in {'pPr','rPr'}:return ''
                return ''.join(visit(c) for c in node)
            text=visit(para).strip()
            attrs={}
            if damaged:attrs=dict(ocr_quality_pending='Word来源包含未支持的公式或对象，请补充原页',original_word_xml=damaged)
            if text:
                style=para.find('./'+W+'pPr/'+W+'pStyle')
                heading=style.get(W+'val','') if style is not None else ''
                if source!='word/document.xml':attrs.update(source_region='header_footer',structure_role='annotation')
                add('heading' if heading.lower().startswith('heading') else 'paragraph',text,source,attributes=attrs)
            for relative,rid in images:
                add('figure','配图',source,attributes=dict(source_asset_relpath=relative,word_relationship_id=rid,asset_status='pending'))
            return text
        def table(element):
            rows=[];vertical={};damaged=[]
            for tr in element.findall(W+'tr'):
                cells=[]
                for tc in tr.findall(W+'tc'):
                    # Image blocks are retained alongside the table in source order.
                    before=len(blocks);texts=[paragraph(p) for p in tc.findall(W+'p')]
                    text=' / '.join(t for t in texts if t).replace('|',r'\|')
                    damaged.extend(xml for b in blocks[before:] for xml in b.attributes.get('original_word_xml',[]))
                    blocks[before:]=[b for b in blocks[before:] if b.block_type=='figure']
                    span=tc.find('./'+W+'tcPr/'+W+'gridSpan')
                    width=int(span.get(W+'val','1') if span is not None else 1)
                    merge=tc.find('./'+W+'tcPr/'+W+'vMerge');column=len(cells)
                    if merge is not None and merge.get(W+'val')!='restart':text=vertical.get(column,text)
                    for c in range(column,column+width):
                        if merge is not None:vertical[c]=text
                        else:vertical.pop(c,None)
                    cells.extend([text]*width)
                rows.append(cells)
            width=max(map(len,rows),default=0)
            rows=[r+['']*(width-len(r)) for r in rows]
            if rows:
                markdown='\n'.join(['| '+' | '.join(rows[0])+' |','| '+' | '.join(['---']*width)+' |',*['| '+' | '.join(r)+' |' for r in rows[1:]]])
                attrs=dict(original_word_xml=ET.tostring(element,encoding='unicode'))
                if damaged:attrs['ocr_quality_pending']='表格含未支持的Word公式或对象，请补充PDF原页'
                add('table',markdown,source,table_header=rows[0],table_rows=rows[1:],attributes=attrs)
        container=root.find(W+'body') if source=='word/document.xml' else root
        for element in list(container) if container is not None else []:
            if element.tag==W+'p':paragraph(element)
            elif element.tag==W+'tbl':table(element)
    book=CanonicalBook(name,'docx',blocks,'exercise-docx-structured-v1',warnings=warnings)
    return book,warnings
