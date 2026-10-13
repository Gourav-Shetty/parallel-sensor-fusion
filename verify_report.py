from docx import Document

mine = Document(r'C:\Users\unusu\Downloads\PC report - Gourav R Shetty.docx')
hers = Document(r'C:\Users\unusu\Downloads\PC report.docx')

print('paras mine/hers:', len(mine.paragraphs), len(hers.paragraphs))
ms = [(p.style.name, p.text.strip()[:30]) for p in mine.paragraphs]
hs = [(p.style.name, p.text.strip()[:30]) for p in hers.paragraphs]
n = 0
for i, (a, b) in enumerate(zip(ms, hs)):
    if a[0] != b[0]:
        print('STYLE DIVERGE at P%d: mine=%s hers=%s' % (i, a, b))
        n += 1
        if n > 5:
            break
else:
    print('style-seq identical over', len(ms), 'paras')
print('author:', mine.core_properties.author)
for j, s in enumerate(mine.inline_shapes):
    assert s.width == hers.inline_shapes[j].width, j
print('image widths exact')
