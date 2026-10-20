"""Create wholly fictional 8772 fixtures. Refuse nonempty/mismatched libraries."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def seed(data, port=8772):
    import httpx
    import pymupdf as fitz
    from scripts.rag_permissions import grant
    root=Path(data).resolve()
    if not root.is_relative_to(Path('/private/tmp')) or port not in {8772,8774} or not root.name.startswith(f'p18-qa-{port}-') or not (root/'.qa-integration-fixture').is_file():
        raise ValueError('Only the marked new 8772 fixture directory is allowed.')
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,headers={'X-P18-Client':'workbench'}) as client:
        config=client.get('/api/config');config.raise_for_status()
        if Path(config.json()['data_directory']).resolve()!=root or client.get('/api/documents').json():
            raise ValueError('Data directory mismatch or library is not empty; no changes made.')
        specs=[('虚构项目基本信息.pdf',['虚构项目基本信息\n项目名称：星桥研发演示。项目负责人：林晓岚。项目导师：周明远。\n所有人物、项目和内容完全虚构。'],True),
          ('虚构接口与排查.pdf',['虚构接口与排查\n接口请求示例：POST /api/reservations，JSON：{"device_id":"DEMO-001","duration":60}。\ndevice_id为string类型，必填。预约时长上限为120分钟。\n付款请求一直没有响应时，检查网络连通性、请求地址和超时配置，核对请求日志，再重试虚构测试请求。\n全部内容完全虚构，仅供验收。'],True),
          ('虚构本地纪要.pdf',['虚构项目负责人内部纪要\n项目负责人字段的本地备注：LOCAL_ONLY_8772，不允许发送。\n全部内容完全虚构，仅本地查看，不授予外发许可。'],False),
          ('虚构九页预算验收.pdf',[f'虚构预算验收第{n}条\n项目资料规范第{n}项：每次选择后均须核对本轮证据。不同条款保留独立身份及原文来源。全部内容完全虚构，用于九组证据预算边界验收。' for n in range(1,10)],True)]
        manifest=[]
        for name,pages,external in specs:
            pdf=fitz.open()
            for text in pages:
                page=pdf.new_page();page.insert_textbox(fitz.Rect(45,60,550,780),text,fontname='china-s',fontsize=13)
            raw=pdf.tobytes();pdf.close()
            response=client.post('/api/documents',files={'files':(name,raw,'application/pdf')});response.raise_for_status();identifier=response.json()[0]['id']
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                response=client.get('/api/documents/'+identifier);response.raise_for_status();doc=response.json()
                if doc['state'] in {'ready','review','failed','held'}:break
                time.sleep(.25)
            if doc['state']!='ready':raise ValueError('Fixture is not ready. Stop for inspection; no review is auto-approved.')
            if external:grant(root,identifier,doc['revision'],'虚构样例验收人员','fictional',True)
            manifest.append({'name':name,'id':identifier,'revision':doc['revision'],'allowed':external})
        (root/'fixture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        print('Created four fictional PDFs. Local Qwen indexing may still be running. No external API called.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,required=True);args=parser.parse_args();seed(args.data_dir)
