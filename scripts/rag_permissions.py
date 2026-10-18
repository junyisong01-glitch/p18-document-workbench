"""Explicit local operator grant; SQLite is opened read-only, no implicit grants."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag import permission_fingerprint


def grant(data, identifier, revision, reviewer, classification, confirm=False, revoke=False):
    data=Path(data).resolve();path=data/'rag-permissions.json'
    if not confirm:raise ValueError('必须使用--confirm-external明确确认脱敏/虚构文档及当前版本可以外发。')
    with sqlite3.connect((data/'workbench.sqlite3').as_uri()+'?mode=ro',uri=True) as c:
        row=c.execute('select body from documents where id=?',(identifier,)).fetchone()
    if not row:raise ValueError('文档不存在。')
    doc=json.loads(row[0])
    if doc['revision']!=revision or doc['state']=='deleted':raise ValueError('文档版本不匹配或已删除。')
    if not reviewer.strip():raise ValueError('请填写人工确认人。')
    values=json.loads(path.read_text()) if path.exists() else {}
    if revoke:values.pop(identifier,None)
    else:values[identifier]={'revision':revision,'fingerprint':permission_fingerprint(doc),'reviewer':reviewer.strip(),
                              'classification':classification,'allow_external':True}
    with tempfile.NamedTemporaryFile(mode='w',dir=data,delete=False,encoding='utf-8') as f:
        os.chmod(f.name,0o600);json.dump(values,f,ensure_ascii=False,indent=2);temp=f.name
    os.replace(temp,path)
    return path


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--document-id',required=True)
    p.add_argument('--revision',type=int,required=True);p.add_argument('--reviewer',required=True)
    p.add_argument('--classification',choices=['fictional','deidentified'],required=True)
    p.add_argument('--confirm-external',action='store_true');p.add_argument('--revoke',action='store_true')
    a=p.parse_args()
    try:print(grant(a.data_dir,a.document_id,a.revision,a.reviewer,a.classification,a.confirm_external,a.revoke))
    except (OSError,ValueError,sqlite3.Error):p.exit(1,'许可操作失败，请核对路径、版本和人工确认参数；未输出文档内容。\n')
