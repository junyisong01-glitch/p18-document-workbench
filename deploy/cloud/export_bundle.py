"""Build a fresh demo deployment bundle, without copying local credentials.

Never edits the source runtime. Uses SQLite backup, then strips authentication
state and keeps only the original classified 6 + 30 demonstration documents.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import secrets
import shutil
import sqlite3
import tarfile

USERS = ('demo_manager','qichen_rd_head','qichen_prd_head','qichen_fin_head','qichen_hr_head','qichen_adm_head','qichen_rd','qichen_qa','qichen_ops','qichen_prd','qichen_fin','qichen_hr','qichen_adm','qichen_guest')


def database_snapshot(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as old, sqlite3.connect(target) as new:
        old.backup(new)


def export(source, live, destination):
    if destination.exists():
        raise ValueError('Use a new output directory; never overwrite a deployment')
    destination.mkdir(parents=True)
    ignore = shutil.ignore_patterns('__pycache__', '*.pyc', 'node_modules', '.DS_Store', '.env', '*.local.json', '*.log')
    for name in ['app','scripts','config','frontend/src','frontend/public','deploy/cloud']:
        if (source/name).is_dir():
            shutil.copytree(source/name, destination/name, ignore=ignore)
    # Only the active frontend build, not historical helper pages or fixtures.
    index=(source/'web/app/index.html').read_text()
    assets=re.findall(r'/(assets/[^"\s]+)',index)
    if len(assets)!=2:raise ValueError('Review changed frontend build outputs before exporting')
    (destination/'web/app/assets').mkdir(parents=True)
    shutil.copy2(source/'web/app/index.html',destination/'web/app/index.html')
    for asset in assets:shutil.copy2(source/'web/app'/asset,destination/'web/app'/asset)
    for name in ['requirements.txt','requirements-semantic.txt','requirements-llm.txt','requirements-docling.txt','README.md','frontend/package.json','frontend/package-lock.json','frontend/index.html','frontend/vite.config.ts','frontend/tsconfig.json','frontend/tsconfig.app.json','frontend/tsconfig.node.json','frontend/tailwind.config.js','frontend/postcss.config.js','frontend/components.json','frontend/eslint.config.js']:
        if (source/name).is_file():
            (destination/name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source/name, destination/name)
    # No old path to a private historical source is shipped.
    (destination/'config/qichen-libraries.json').write_text(json.dumps({'enabled':False,'data_dir':'runtime/business-workflow','acl':{}}))
    (destination/'config/business.json').write_text(json.dumps({'data_dir':'runtime/business-workflow'}))
    cfg=json.loads((destination/'config/demo-v1.json').read_text())
    cfg.update(converter='/usr/bin/soffice', docling_python='/usr/local/bin/python', model_cache='.cache/huggingface/hub')
    (destination/'config/demo-v1.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2))
    counts={}
    for name, count in [('demo-v1-experience',6),('business-workflow',30)]:
        origin=live/'runtime'/name; target=destination/'runtime'/name
        database_snapshot(origin/'workbench.sqlite3',target/'workbench.sqlite3')
        with sqlite3.connect(target/'workbench.sqlite3') as c:
            c.execute('PRAGMA secure_delete=ON')
            ids=[r[0] for r in c.execute('SELECT document_id FROM library_metadata ORDER BY document_id')]
            if len(ids)!=count: raise ValueError('Unexpected seed count '+name)
            placeholders=','.join('?' for _ in ids)
            tables=[r[0]for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                columns=[r[1]for r in c.execute('PRAGMA table_info("'+table+'")')]
                if table=='documents':c.execute('DELETE FROM documents WHERE id NOT IN ('+placeholders+')',ids)
                elif 'document_id'in columns:c.execute('DELETE FROM "'+table+'" WHERE document_id NOT IN ('+placeholders+')',ids)
            for table in ['library_sessions','library_login_attempts','account_invitations','business_role_audit','external_audit','business_events','business_edits','business_grants']:
                if table in tables:c.execute('DELETE FROM "'+table+'"')
            if name=='demo-v1-experience':
                marks=','.join('?'for _ in USERS)
                c.execute('DELETE FROM business_profiles WHERE username NOT IN ('+marks+')',USERS)
                c.execute('DELETE FROM library_accounts WHERE username NOT IN ('+marks+')',USERS)
                if c.execute('SELECT count(*) FROM library_accounts').fetchone()[0]!=14:raise ValueError('Expected 14 demo accounts')
                # Passwords are unknown random values; cards use new one-time
                # challenges. Neither old salts/hashes nor new passwords leave here.
                for user in USERS:
                    salt=secrets.token_hex(16)
                    hashed=hashlib.scrypt(secrets.token_bytes(48),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
                    c.execute('UPDATE library_accounts SET salt=?,password=?,active=1 WHERE username=?',(salt,hashed,user))
                    c.execute('UPDATE business_profiles SET is_demo=1 WHERE username=?',(user,))
            c.commit();c.execute('VACUUM')
        for identifier in ids:
            shutil.copytree(origin/'files'/identifier,target/'files'/identifier,ignore=ignore)
        for p in (origin/'qdrant').rglob('*'):
            if not p.is_file()or p.name=='.lock'or p.name.endswith(('-wal','-shm')):continue
            out=target/'qdrant'/p.relative_to(origin/'qdrant');out.parent.mkdir(parents=True,exist_ok=True)
            if p.suffix in {'.sqlite','.sqlite3'}:database_snapshot(p,out)
            else:shutil.copy2(p,out)
        if name=='business-workflow':
            seed=json.loads((origin/'business-seed.json').read_text())
            (target/'business-seed.json').write_text(json.dumps({'acl':{k:v for k,v in seed['acl'].items()if k in ids}},ensure_ascii=False))
        else:(target/'business-demo-enabled.json').write_text('{"enabled":true}')
        counts[name]=len(ids)
    (destination/'runtime/tmp').mkdir()
    (destination/'CLOUD-DEMO.json').write_text(json.dumps({'isolated_demo':True,'accounts':14,'documents':counts,'sessions_exported':False,'passwords_rotated':True,'personal_keys_exported':False,'weights_included':False},indent=2))
    files={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest()for p in destination.rglob('*')if p.is_file()}
    (destination/'BUNDLE-SHA256.json').write_text(json.dumps(files,indent=2))
    archive=destination.with_suffix('.tar.gz')
    with tarfile.open(archive,'w:gz')as tar:tar.add(destination,arcname=destination.name)
    print(json.dumps({'directory':str(destination),'archive':str(archive),'bytes':archive.stat().st_size,'documents':counts,'accounts':14}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--live',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    export(a.source.resolve(),a.live.resolve(),a.output.resolve())
