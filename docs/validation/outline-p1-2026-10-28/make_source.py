"""Unseen synthetic two-chapter textbook, exported as a MinerU ZIP."""
import io
import json
import sys
import zipfile


def payload():
    pages = [dict(page_idx=0, blocks=[dict(type='index', content='目录\n第一章 集合……1\n第一节 基本概念……1\n第二章 映射……3\n第一节 基本性质……3')])]
    for page, title, section, value in [(4, '第一章 集合', '第一节 基本概念', '甲'), (6, '第二章 映射', '第一节 基本性质', '乙')]:
        pages.append(dict(page_idx=page, blocks=[
            dict(type='text', content=title), dict(type='text', content=section),
            dict(type='text', content=f'条件{value}：定义与条件保留在本章。'),
            dict(type='paragraph_title', content='一、附加说明'),
            dict(type='text', content=f'本段条件{value}不会因为简化目录而被删除。'),
            dict(type='equation', content='$$f(x)=x^2+1$$'),
            dict(type='table', content='| 参数 | 值 |\n|---|---|\n| a | 2 |\n| b | 3 |', captions=[dict(content=f'表{page} 参数')]),
            dict(type='paragraph_title', content='自测训练'),
            dict(type='text', content=f'1. 在条件{value}下，计算函数在 x=2 时的值。'),
        ]))
    return dict(metadata=dict(producer=dict(name='mineru', version='4.0.12'), document=dict(page_count=8)), pages=pages)


if __name__ == '__main__':
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('structured_content.json', json.dumps(payload(), ensure_ascii=False))
    sys.stdout.buffer.write(output.getvalue())
