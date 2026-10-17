from docx import Document
from app.parser import parse_word
from app.word_structure import table_structure, table_text, associate_preview, compatibility_copy
import pymupdf as fitz
import zipfile


def test_physical_merges_and_equal_cells(tmp_path):
    d=Document(); t=d.add_table(rows=4,cols=3)
    t.cell(0,0).merge(t.cell(0,2)).text='横向标题'
    t.cell(1,0).merge(t.cell(3,0)).text='纵向内容'
    t.cell(1,1).text=t.cell(1,2).text='相同文字'
    shape=table_structure(t,'table-1')
    assert shape['cells'][0]['colspan']==3
    assert next(c for c in shape['cells'] if c['text']=='纵向内容')['rowspan']==3
    assert table_text(shape).count('横向标题')==1
    assert table_text(shape).count('纵向内容')==1
    assert table_text(shape).count('相同文字')==2


def test_empty_paragraph_metadata_and_separator_notes(tmp_path):
    d=Document();d.add_paragraph('');d.add_paragraph('真实正文');p=tmp_path/'x.docx';d.save(p)
    with zipfile.ZipFile(p,'a') as z:
        z.writestr('word/footnotes.xml','<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:footnote w:type="separator" w:id="0"><w:p/></w:footnote></w:footnotes>')
    r=parse_word(p)
    assert r['blocks'][0]['text']=='' and not r['blocks'][0]['has_objects']
    assert not any(i['kind']=='notes' for i in r['issues'])
    with zipfile.ZipFile(p,'a') as z:
        z.writestr('word/endnotes.xml','<w:endnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:endnote w:id="2"><w:p><w:r><w:t>实际注释</w:t></w:r></w:p></w:endnote></w:endnotes>')
    assert any(i['kind']=='notes' for i in parse_word(p)['issues'])


def test_preview_unique_repeat_cross_page(tmp_path):
    path=tmp_path/'preview.pdf'
    pdf=fitz.open()
    pdf.new_page().insert_text((50,50),'unique anchor words\nrepeat anchor words\nrepeat anchor words\ncross page')
    pdf.new_page().insert_text((50,50),'continuation words')
    pdf.save(path);pdf.close()
    blocks=[dict(text=t) for t in ['unique anchor words','repeat anchor words','cross page continuation words','missing anchor words']]
    associate_preview(blocks,path,'original')
    assert blocks[0]['preview_pages']=={'original':1}
    assert all(not b['preview_pages'] for b in blocks[1:])


def test_compatibility_copy_preserves_original_and_text(tmp_path):
    d=Document();d.add_paragraph('中文 technical 正文');source=tmp_path/'x.docx';d.save(source)
    original=source.read_bytes();copy=tmp_path/'preview.docx';compatibility_copy(source,copy)
    assert source.read_bytes()==original
    assert Document(copy).paragraphs[0].text==d.paragraphs[0].text
    assert Document(copy).paragraphs[0].runs[0].font.name=='Arial Unicode MS'

from test_workbench import client, upload, wait, HEADERS
from test_chunking import wait_chunks, sample
from app.chunking import prepare, configuration
from app import main


def test_merged_table_chunks_keep_entire_group(tmp_path):
    d=Document();t=d.add_table(rows=4,cols=2);t.cell(0,0).merge(t.cell(3,0)).text='关联行组'
    for i in range(4):t.cell(i,1).text='内容'*100
    path=tmp_path/'x.docx';d.save(path);r=parse_word(path)
    doc=sample(r['blocks']);doc['result']=r
    _,chunks=prepare(doc,{**configuration(),'target_chars':100})
    assert len(chunks)==1 and chunks[0]['text'].count('关联行组')==1
    assert chunks[0]['tables'][0]['cells'][0]['rowspan']==4


def test_reparse_invalidates_and_archives(client):
    doc=wait(client,upload(client)['id']);wait_chunks(client,doc['id'])
    url=f"/api/documents/{doc['id']}/reparse"
    assert client.post(url,json={'revision':0},headers=HEADERS).status_code==409
    response=client.post(url,json={'revision':1},headers=HEADERS)
    assert response.status_code==200
    new=wait(client,doc['id']);assert new['revision']==2 and new.get('review_decision') is None
    assert (main.folder_for(doc['id'])/'history/revision-1.json').exists()
    result=wait_chunks(client,doc['id'])
    assert all(c['revision']==2 for c in result['chunks'])
    assert client.get(f"/api/documents/{doc['id']}/preview/original/1?zoom=4").status_code==422
