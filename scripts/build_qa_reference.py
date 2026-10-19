"""Extract same-origin classes from approved references without changing the originals."""
from pathlib import Path
import re,json
root=Path(__file__).resolve().parents[1]/'web/qa'; styles={}; templates={}
for p in sorted(root.glob('[0-9][0-9]-*.html')):
 text=p.read_text();body=re.search(r'<body>(.*?)</body>',text,re.S)[1]
 def sub(m):
  value=m[1]
  if value not in styles:styles[value]='q'+str(len(styles))
  return 'class="'+styles[value]+'"'
 templates[p.name[:2]]=re.sub(r'style="([^"]*)"',sub,body)
(root/'live-templates.json').write_text(json.dumps(templates,ensure_ascii=False))
css=':host{display:block;font-family:"Noto Sans SC","Noto Sans CJK SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;color:#1b1d23;font-size:14px;line-height:1.7}button,input,select{font-family:inherit}button{cursor:pointer}a{color:#5e6ad2;text-decoration:none}[hidden]{display:none!important}button:disabled{opacity:.5;cursor:default}\n'
css+='\n'.join('.'+name+'{'+value+'}' for value,name in styles.items())
(root/'live-reference.css').write_text(css)
