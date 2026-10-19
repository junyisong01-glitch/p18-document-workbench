/* Static design demonstration. Only local templates/tokens are fetched. */
(() => {
  const initial=new URLSearchParams(location.search).get('qa-preview');
  if(!initial)return;
  const {pages,evidence,create}=window.P18QADemo;
  const demo=create(), cache=new Map();
  let current=pages[initial]?initial:'01',generation=0,timer,noticeTimer,closeTarget='04',panelOrigin='10',sentSnapshot=null;
  function reset(){demo.reset();sentSnapshot=null;}
  if(current==='12')demo.enterFollow();
  const host=document.createElement('div'), root=host.attachShadow({mode:'open'});
  document.documentElement.style.visibility='hidden';
  document.body.replaceChildren(host);document.body.style.margin='0';
  document.head.querySelectorAll('link[rel="stylesheet"]').forEach(link=>link.remove());
  const font=document.createElement('link');font.rel='stylesheet';font.href='https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap';document.head.append(font);
  async function template(id){if(!cache.has(id)){const response=await fetch(`/static/qa/${pages[id]}.html`);if(!response.ok)throw new Error('无法读取界面模板');cache.set(id,await response.text());}return cache.get(id);}
  function fail(){root.textContent='无法打开模拟界面，请刷新后重试。';document.documentElement.style.visibility='';}
  function go(id,{auto=false,focus=null}={}){clearTimeout(timer);current=id;history.pushState(null,'',`?qa-preview=${id}`);render({auto,focus}).catch(fail);}
  async function render({auto=false,focus=null}={}){
    const ticket=++generation;
    const doc=new DOMParser().parseFromString(await template(current),'text/html');
    const tokenResponse=await fetch('/static/qa/tokens.css');if(!tokenResponse.ok)throw new Error('无法读取设计令牌');const tokens=await tokenResponse.text();
    if(ticket!==generation)return;
    document.title=`${doc.title} · 纯前端模拟`;
    const style=document.createElement('style');
    style.textContent=tokens.replace(':root{',':host{')+doc.querySelector('style').textContent.replace('body{',':host{')+`
      :host{display:block}button:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
      .qa-file-name{color:var(--text);font-weight:500!important}.qa-summary{color:var(--text-2);margin-top:2px}
      .qa-source-icons{gap:8px!important}.qa-clickable{cursor:pointer}.qa-local-status{white-space:nowrap}
      .qa-notice{position:fixed;bottom:126px;left:50%;transform:translateX(-50%);max-width:620px;padding:10px 18px;border:1px solid var(--line-card);border-radius:10px;background:white;color:var(--text-2);font-size:13px;box-shadow:var(--sh-composer);z-index:30}
      .qa-local-error{font-size:13px;color:var(--warn-text);margin-top:8px}
      [role=dialog]{max-height:calc(100vh - 48px);overflow:auto!important}
    `;
    root.replaceChildren(style,...doc.body.childNodes);
    const all=selector=>[...root.querySelectorAll(selector)];
    const exact=text=>all('*').find(e=>e.children.length===0&&e.textContent.trim()===text);
    const rename=(a,b)=>{const e=exact(a);if(e)e.textContent=b;};
    const click=(element,action,label)=>{if(!element)return;element.classList.add('qa-clickable');element.onclick=action;if(element.tagName!=='BUTTON'&&element.tagName!=='A'){element.tabIndex=0;element.setAttribute('role','button');element.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();action(e);}};}if(label)element.setAttribute('aria-label',label);};
    rename('DeepSeek 已配置','纯前端模拟 · 未连接 API');
    rename('本地测试环境 · 文档默认不外发','虚构演示 · 历史不永久保存');
    rename('已发送 3 条证据','已模拟发送 3 条证据（未外发）');
    rename('DeepSeek 正在根据所选证据生成回答，完成后一次性显示','正在模拟生成参考回答，未调用 DeepSeek');
    all('span').forEach(e=>{if(e.textContent.startsWith('已完成 ·')||e.textContent.startsWith('部分回答 ·'))e.textContent='模拟回答 · '+e.textContent.replace('DeepSeek 生成','虚构内容');});
    rename('根据当前可用的文档证据，无法确定。','【模拟回答】根据当前可用的文档证据，无法确定。');
    // Explicitly identify the fictional answer on the follow-up page too.
    if(current==='12'){const answer=all('div').find(e=>e.style.lineHeight==='1.9'&&e.textContent.includes('林晓岚'));if(answer)answer.prepend('【模拟回答】');}
    all('span').filter(e=>e.style.display==='flex'&&e.style.gap==='4px'&&e.children.length&&[...e.children].every(c=>['PDF','DOC','XLS'].includes(c.textContent))).forEach(e=>e.classList.add('qa-source-icons'));
    const notice=document.createElement('div');notice.className='qa-notice';notice.setAttribute('role','status');notice.hidden=true;root.append(notice);
    const tell=text=>{notice.textContent=text;notice.hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>notice.hidden=true,5000);};
    const localError=message=>{let e=root.querySelector('.qa-local-error');if(!e){e=document.createElement('p');e.className='qa-local-error';e.setAttribute('role','alert');root.querySelector('input[type=checkbox]')?.parentElement.parentElement.parentElement.append(e);}e.textContent=message;};
    click(exact('＋ 新对话'),()=>{reset();go('01');});
    all('aside > div').filter(e=>['支付接口测试问题','项目负责人与导师','接口超时时间','项目周期与排期','文档解析测试'].includes(e.textContent.trim())).forEach(e=>click(e,()=>{reset();if(e.textContent==='项目负责人与导师'){demo.enterFollow();go('12');}else go('10');}));
    all('nav > div').slice(1,3).forEach(e=>click(e,()=>tell('隔离设计预览未接入文档管理或知识检索服务。')));
    const input=root.querySelector('input[type=text]'), send=all('button').find(b=>b.textContent.trim()==='↑');
    const locked=['02','04','05','06','07','08','12'].includes(current);
    if(input){input.disabled=locked;send.disabled=locked;if(!locked){send.onclick=()=>{if(!input.value.trim())return tell('请输入问题。此处只运行虚构模拟流程。');reset();demo.state.question=input.value.trim();go('02',{auto:true});};input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();send.click();}};}}
    if(current==='01'){const grid=all('div').find(e=>e.style.display==='grid');[...grid.children].forEach(card=>click(card,()=>{reset();demo.state.question=card.firstElementChild.textContent;go('02',{auto:true});}));}
    if(['06','07'].includes(current)) {
      const selected=demo.snapshot();
      all('input[type=checkbox]').forEach((check,index)=>{
        const item=selected[index],row=check.parentElement;
        if(!item){row.parentElement.remove();return;}
        const name=row.querySelector('b');
        if(name.textContent!==item.name){name.textContent=item.name;name.parentElement.parentElement.children[1].textContent=item.text;}
        const icon=row.children[1];icon.textContent=item.type;icon.style.background=item.type==='PDF'?'#fdecea':'#e8f0fe';icon.style.color=item.type==='PDF'?'#b0402c':'#2f5fbf';
      });
      rename('已选 3 条',`已选 ${selected.length} 条`);
    }
    rename('已模拟发送 3 条证据（未外发）',`已模拟发送 ${demo.selected().length} 条证据（未外发）`);
    const checks=all('input[type=checkbox]');
    checks.forEach(check=>{
      const row=check.parentElement, group=row.parentElement;
      const name=row.querySelector('b'), id=evidence.findIndex(e=>e.name===name?.textContent.trim());
      if(id<0)return;
      name.classList.add('qa-file-name');
      const info=name.parentElement.parentElement, summary=info.children[1];summary?.classList.add('qa-summary');
      const status=name.nextElementSibling;if(status){status.classList.add('qa-local-status');status.style.marginLeft='auto';}
      check.setAttribute('aria-label',`选择虚构证据 ${id+1}`);check.disabled=!evidence[id].allowed;
      check.checked=demo.state.selected.has(id)&&evidence[id].allowed;
      const sync=()=>{check.checked=demo.state.selected.has(id)&&!check.disabled;group.style.boxShadow=check.checked?'inset 3px 0 0 #5e6ad2':'none';group.style.background=check.checked?'#f8f9ff':'#fff';const count=all('b').find(b=>b.style.fontSize==='15px');if(count)count.textContent=demo.selected().length;};sync();
      check.onchange=()=>{demo.select(id,check.checked);sync();root.querySelector('.qa-local-error')?.remove();};
      const toggle=row.lastElementChild;
      click(toggle,()=>{
        const open=toggle.textContent.trim()==='⌃';
        if(open){const detail=info.querySelector('[data-detail]')||info.children[2];detail?.remove();summary.style.whiteSpace='nowrap';toggle.textContent='⌄';}
        else {summary.style.whiteSpace='normal';toggle.textContent='⌃';const detail=document.createElement('div');detail.dataset.detail='true';detail.style.cssText='margin-top:8px;display:flex;flex-direction:column;gap:8px';const text=document.createElement('div');text.style.cssText='font-size:14px;line-height:1.85;color:#2a2e3a;background:#f7f8fa;border-radius:8px;padding:10px 14px';text.textContent=evidence[id].text;detail.append(text);const action=document.createElement('button');action.style.cssText='font-size:13px;border:0;background:transparent;color:#6b7080;padding:4px 8px;text-align:left';action.textContent='在右侧查看原文 →';action.onclick=()=>{demo.state.source=id;go('05');};detail.append(action);info.append(detail);}
      },`展开虚构证据 ${id+1}`);
    });
    // Confirmation is a separate, entirely simulated step; selections stay in memory only.
    all('button').forEach(button=>{
      const text=button.textContent.trim();
      if(text==='确认外发范围')button.onclick=()=>{if(!demo.canConfirm())return localError('请至少选择 1 条可外发的证据');closeTarget=current;go('06',{focus:'dialog'});};
      if(text==='仅在本地查看')button.onclick=()=>tell('本地查看：所有展示均为虚构样例；未生成真实回答，未发送数据。');
      if(text==='取消勾选')button.onclick=()=>{const c=button.closest('[style*="border-top"]')?.querySelector('input[type=checkbox]');if(c){c.checked=false;c.onchange();}};
      if(text==='在右侧查看原文 →')button.onclick=()=>go('05');
      if(['重新选择证据','查看检索依据','查看检索候选','返回修改证据','返回选择','调整选择'].includes(text))button.onclick=()=>go(demo.state.follow?'12':'04');
      if(text==='重新检索')button.onclick=()=>go('02',{auto:true});
      if(text==='修改问题')button.onclick=()=>{if(input&&!input.disabled){input.focus();}else{reset();go('01',{focus:'input'});}};
      if(text==='手动重试')button.onclick=()=>{closeTarget='09';go('06',{focus:'dialog'});};
      if(text==='打开完整文档 ↗')button.onclick=()=>tell('虚构原文纸页仅为布局演示，没有可下载的真实文件。');
      if(text==='复制')button.onclick=async()=>{try{await navigator.clipboard.writeText('【虚构模拟回答】'+button.parentElement.parentElement.querySelector('[style*="line-height:1.9"]').textContent);tell('已复制虚构模拟回答。');}catch{tell('复制未获浏览器许可，请手动选择文本。');}};
      if(['返回文档管理','检查配置','重试预览'].includes(text))button.onclick=()=>tell('开发文案对照，仅展示恢复操作；此预览不操作业务服务。');
    });
    if(['06','07'].includes(current)){
      const overlay=all('div').find(e=>e.style.position==='absolute'&&e.style.inset==='0px');
      const modal=overlay.firstElementChild;modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-label','确认模拟发送');modal.tabIndex=-1;
      const title=modal.firstElementChild;title.textContent='确认模拟发送给 DeepSeek';
      rename('确认后，以上内容将发送到外部 AI。','虚构演示：仅模拟发送，不连接外部 AI。');
      rename('服务：api.deepseek.com · 模型：deepseek-flash · 必要历史：无 · 授权校验：已通过','模拟配置：api.deepseek.com · deepseek-flash · 不执行网络请求');
      const label=all('span').find(e=>e.textContent.startsWith('发送的证据 ·'));
      label.textContent=`模拟发送的证据 · ${demo.selected().length} 条`;
      const list=label.nextElementSibling;const sample=list.firstElementChild.cloneNode(true);list.replaceChildren();
      for(const item of demo.snapshot()){const row=sample.cloneNode(true);row.firstElementChild.textContent=item.type;row.firstElementChild.style.background=item.type==='PDF'?'#fdecea':'#e8f0fe';row.firstElementChild.style.color=item.type==='PDF'?'#b0402c':'#2f5fbf';row.lastElementChild.textContent=item.name;list.append(row);}
      const question=exact('本轮问题').nextElementSibling;question.textContent=demo.state.question;
      const detail=all('div').find(e=>e.style.lineHeight==='1.85'&&e.style.borderTop&&modal.contains(e));
      if(detail){detail.replaceChildren();for(const item of demo.snapshot()){const name=document.createElement('b');name.style.cssText='font-weight:500;color:#1b1d23';name.textContent=item.name;detail.append(name,document.createElement('br'),document.createTextNode(item.text),document.createElement('br'));}if(demo.state.follow)detail.append(document.createTextNode('必要历史（虚构）：上一轮项目负责人为林晓岚；仅辅助理解追问，不作为本轮事实证据。'));}
      const cancel=exact('取消'),confirm=exact('确认发送');confirm.textContent='确认模拟发送';confirm.onclick=()=>{if(!demo.canConfirm())return tell('没有可选择的虚构证据。');sentSnapshot=demo.snapshot();go('08',{auto:true});};
      const cancelModal=()=>go(closeTarget,{focus:'confirm'});cancel.onclick=cancelModal;
      [...overlay.parentElement.children].filter(e=>e!==overlay).forEach(e=>e.inert=true);
      overlay.onclick=e=>{if(e.target===overlay)cancelModal();};
      modal.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();cancelModal();}if(e.key==='Tab'){const focusable=[...modal.querySelectorAll('button,a,[tabindex]')].filter(e=>!e.disabled);const first=focusable[0],last=focusable.at(-1);if(e.shiftKey&&root.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&root.activeElement===last){e.preventDefault();first.focus();}}};
      const expand=modal.querySelector('a');expand.onclick=e=>{e.preventDefault();go(current==='06'?'07':'06',{focus:'dialog'});};
      modal.focus();
    }
    const panel=all('aside').find(e=>e.style.flex.includes('400px'));
    if(panel){
      const source=evidence[demo.state.source]||evidence[0];
      const close=exact('×');click(close,()=>go(current==='05'?'04':panelOrigin), '关闭原文栏');
      const card=panel.children[1],fileInfo=card.children[1];card.firstElementChild.textContent=source.type;fileInfo.firstElementChild.textContent=source.name;
      const meta=fileInfo.lastElementChild;meta.textContent=source.type==='PDF'?'虚构预览 · v1 · PDF · 第三章 · 第 5 页':'虚构预览 · v1 · Word · 结构位置演示';
      if(demo.state.source!==0){const article=panel.querySelector('article');article.replaceChildren();const title=document.createElement('div');title.style.cssText='font-size:15px;font-weight:500;color:#1b1d23';title.textContent=source.name+' · 虚构原文';article.append(title,document.createTextNode(source.text));}
      const texts=all('div').filter(e=>panel.contains(e)&&e.style.background==='rgb(255, 246, 204)');if(demo.state.source!==0)texts.forEach(e=>e.textContent=source.text);
      const tabs=[exact('原文'),exact('检索信息')],content=panel.lastElementChild;
      click(tabs[1],()=>{content.replaceChildren();const p=document.createElement('p');p.style.cssText='font-size:13px;color:#6b7080';p.textContent=`虚构检索信息：${source.name}；演示版本 v1；来源编号为本地占位，未进行真实后端有效性或许可校验。`;content.append(p);tabs[0].style.borderBottom='0';tabs[1].style.borderBottom='2px solid #5e6ad2';});
      click(tabs[0],()=>render().catch(fail));
      const sourceLabel=all('span').find(e=>panel.contains(e)&&e.textContent==='来源 1 / 2');
      const change=()=>{const second=sourceLabel.textContent==='来源 1 / 2';sourceLabel.textContent=second?'来源 2 / 2':'来源 1 / 2';meta.textContent=second?`虚构第二来源 · v1 · ${source.type} · 无可靠页码`:(source.type==='PDF'?'虚构预览 · v1 · PDF · 第三章 · 第 5 页':'虚构预览 · v1 · Word · 结构位置演示');};
      all('button').filter(b=>panel.contains(b)&&['‹','›'].includes(b.textContent)).forEach(b=>b.onclick=change);
    }
    if(current==='10'&&sentSnapshot){
      const turns=all('main section > div > section'), first=turns[0];
      if(first){
        turns.slice(1).forEach(e=>e.remove());first.firstElementChild.textContent=demo.state.question;
        const answer=first.querySelector('[style*="line-height:1.9"]'),group=answer.parentElement,citation=answer.querySelector('a').cloneNode(true);
        answer.replaceChildren(document.createTextNode('【固定模拟摘录，非模型回答】'));
        sentSnapshot.forEach((item,i)=>{answer.append(document.createTextNode(item.text));const a=citation.cloneNode(true);a.textContent=i+1;a.dataset.evidenceId=item.id;answer.append(a);});
        group.firstElementChild.querySelector('span:last-child').textContent=`模拟回答 · 已完成 · 模拟发送 ${sentSnapshot.length} 条 · 未调用 API`;
        const sources=group.children[2],icons=sources.firstElementChild,iconSample=icons.firstElementChild.cloneNode(true);icons.replaceChildren();
        sentSnapshot.forEach(item=>{const icon=iconSample.cloneNode(true);icon.textContent=item.type;icon.style.background=item.type==='PDF'?'#fdecea':'#e8f0fe';icon.style.color=item.type==='PDF'?'#b0402c':'#2f5fbf';icons.append(icon);});
        sources.querySelector('a').textContent=`引用 ${sentSnapshot.length} 个虚构来源 ›`;
      }
    }
    if(current==='10'&&demo.state.follow&&!sentSnapshot){
      const turns=all('main section > div > section');
      const first=turns[0];
      if(first){turns.slice(1).forEach(e=>e.remove());first.firstElementChild.textContent='她同时是导师吗？';const answer=first.querySelector('[style*="line-height:1.9"]');answer.textContent='【模拟回答】根据当前可用的文档证据，无法确定。虚构资料只说明导师由学院另行指定。';const group=answer.parentElement;[...group.children].filter(e=>e!==answer).forEach(e=>e.remove());}
    }
    if(!['06','07'].includes(current))all('a').forEach(a=>a.onclick=e=>{e.preventDefault();if(current!=='11')panelOrigin=current;demo.state.source=a.dataset.evidenceId!==undefined?Number(a.dataset.evidenceId):(/^[123]$/.test(a.textContent)?Number(a.textContent)-1:(sentSnapshot?.[0]?.id||0));go('11');});
    const rail=all('div').find(e=>e.style.flex==='0 0 40px');click(rail,()=>{panelOrigin=current;go(checks.length?'05':'11');},'展开引用与原文');
    if(focus==='input')input?.focus();if(focus==='confirm')all('button').find(b=>b.textContent==='确认外发范围')?.focus();
    document.documentElement.style.visibility='';
    if(auto&&current==='02')timer=setTimeout(()=>go(demo.state.follow?'12':'04'),1200);
    if(auto&&current==='08')timer=setTimeout(()=>go('10'),1500);
    window.P18QAPreview={mode:current,root,fictional:true};
  }
  window.addEventListener('popstate',()=>{clearTimeout(timer);current=new URLSearchParams(location.search).get('qa-preview');if(!pages[current])current='01';render().catch(fail);});
  render().catch(fail);
})();
