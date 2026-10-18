/* Session state stays in memory; no API keys or long-term chat storage. */
window.P18Rag={create({api,esc,onShow}){
 const $=s=>document.querySelector(s);let session=null,pending=null,turns=[],busy=false,epoch=0,modalEpoch=0,restoreFocus=null;
 function status(text){$('#rag-status').textContent=text;}
 function setBusy(value){busy=value;$('#rag-prepare').disabled=value;$('#rag-clear').disabled=value;}
 function draw(){
  $('#rag-chat').innerHTML=turns.map((t,i)=>`<article class="rag-turn"><h3>你</h3><p class="rag-text">${esc(t.question)}</p><h3>${esc(t.provider)} · AI参考回答</h3><p class="rag-text">${esc(t.answer)}</p><p class="source-note">${esc(t.notice)}</p><div>${t.citations.map((s,j)=>`<button class="secondary" data-rag-cite="${i}" data-source="${j}">[${esc(s.id)}] ${esc(s.document_name)}</button>`).join('')}<button class="text-button" data-rag-basis="${i}">查看检索依据</button></div></article>`).join('');
 }
 async function health(){try{const h=await api('/api/rag');$('#rag-health').textContent=`${h.provider} · ${h.configured?'可准备并逐轮确认发送':'API未配置，其他模块可继续使用'}。${h.error||h.notice}`;}catch(e){$('#rag-health').textContent='问答服务不可用：'+e.message;}}
 function close(){modalEpoch++;$('#rag-modal').close();restoreFocus?.focus();}
 async function openSources(sources){
  restoreFocus=document.activeElement;const dialog=$('#rag-modal');$('#rag-modal-title').textContent='证据与原文核对';
  const choices=sources.flatMap(s=>(s.members||[s]).map(m=>({...m,id:s.id})));
  $('#rag-modal-body').innerHTML=`<p>只读查看本次实际提供的证据。候选勾选、保存选择及重新生成尚未实现。</p><label>来源 <select id="rag-source-select">${choices.map((s,i)=>`<option value="${i}">[${esc(s.id)}] ${esc(s.document_name)} · ${esc(s.section||'文档级')}</option>`).join('')}</select></label><p id="rag-source-status"></p><pre id="rag-source-text" class="rag-text"></pre><p id="rag-source-risk" class="preview-warning"></p><p><a id="rag-source-download" hidden>下载原文件</a> <button id="rag-prev" type="button" disabled>上一页</button> <span id="rag-page"></span> <button id="rag-next" type="button" disabled>下一页</button></p><div id="rag-source-preview"></div>`;
  dialog.showModal();$('#rag-modal-close').focus();let page=0,count=0,doc=null;
  function image(){if(!doc||!page)return;$('#rag-page').textContent=`第 ${page}/${count} 页${doc.ext!=='.pdf'?' · 系统转换预览':''}`;$('#rag-prev').disabled=page<=1;$('#rag-next').disabled=page>=count;$('#rag-source-preview').innerHTML=`<img alt="${esc(doc.name)} 原文预览" src="/api/documents/${doc.id}/preview/original/${page}?revision=${doc.revision}">`;}
  async function load(i){
   const token=++modalEpoch,s=choices[i];doc=null;page=0;count=0;$('#rag-prev').disabled=$('#rag-next').disabled=true;
   $('#rag-source-download').hidden=true;$('#rag-page').textContent='';$('#rag-source-text').textContent=s.text;$('#rag-source-preview').textContent='正在核验当前文档版本…';
   $('#rag-source-risk').textContent=(s.risk?.incomplete?'来源存在内容不完整风险。':'')+(s.risk?.quality==='review'?'来源曾需复核，原风险提示保留。':'');$('#rag-source-risk').hidden=!$('#rag-source-risk').textContent;
   try{
    const [d,index]=await Promise.all([api(`/api/documents/${s.document_id}`),api(`/api/documents/${s.document_id}/index`)]);
    if(token!==modalEpoch||!dialog.open)return;
    if(d.revision!==s.revision||!index.searchable||index.token!==s.index_token)throw new Error('引用已失效，不能作为当前有效来源。请重新提问。');
    const meta=await api(`/api/documents/${d.id}/preview/original/meta`);if(token!==modalEpoch||!dialog.open)return;
    doc=d;count=meta.pages;$('#rag-source-download').href=`/api/documents/${d.id}/file/original`;$('#rag-source-download').hidden=false;
    const src=s.sources?.[0]||{};const target=window.P18Search.sourcePage({},d,src);
    $('#rag-source-status').textContent=(src.label||s.section||'文档级来源')+'。'+(d.ext!=='.pdf'?'Word采用系统转换预览，分页可能不同且预览可能不完整。':'PDF使用可靠物理页。');
    if(target&&target<=count){page=target;image();}else{$('#rag-source-status').textContent+=' 当前无法可靠确定对应页，未猜测页码。';$('#rag-source-preview').innerHTML='<button id="rag-browse" type="button">从首页浏览（非片段定位）</button>';$('#rag-browse').onclick=()=>{page=1;image();};}
   }catch(e){if(token===modalEpoch){$('#rag-source-status').textContent=e.message;$('#rag-source-preview').textContent='当前未提供有效原文预览。';}}
  }
  $('#rag-source-select').onchange=e=>load(Number(e.target.value));$('#rag-prev').onclick=()=>{if(page>1){page--;image();}};$('#rag-next').onclick=()=>{if(page<count){page++;image();}};
  if(choices.length)await load(0);
 }
 $('#rag-modal-close').onclick=close;$('#rag-modal').addEventListener('cancel',e=>{e.preventDefault();close();});
 $('#rag-form').onsubmit=async e=>{
  e.preventDefault();if(busy)return;const question=$('#rag-question').value.trim();if(!question)return;
  const token=++epoch;setBusy(true);pending=null;$('#rag-consent').innerHTML='';status('仅在本机检索有效证据，尚未调用外部模型…');
  try{const p=await api('/api/rag/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,session_id:session})});if(token!==epoch)return;session=p.session_id;
   if(p.status!=='prepared'){status(p.message);return;}pending=p;
   $('#rag-consent').innerHTML=`<div class="rag-turn"><h3>发送前核对</h3><p>${esc(p.provider)} · ${esc(p.model)} · ${esc(p.destination)}</p><p>本轮问题：${esc(p.question)}</p><details><summary>将发送的必要历史（${p.history.length}轮）</summary><pre class="rag-text">${esc(p.history.map(t=>'问题：'+t.question+'\n历史回答（仅辅助指代）：'+t.answer).join('\n\n')||'无历史')}</pre></details><p>获准证据 ${p.evidence.length} 组；未授权候选已排除。</p><button class="secondary" id="rag-preview-basis">查看检索依据与实际文本</button><label class="rag-consent-label"><input id="rag-allow" type="checkbox">我已核对本轮问题、以上历史及获准证据，明确允许发送到显示的服务。</label><button class="primary" id="rag-send" disabled>${p.configured?'同意发送并生成参考回答':'API未配置，暂不能生成'}</button></div>`;
   $('#rag-preview-basis').onclick=()=>openSources(p.evidence);$('#rag-allow').onchange=e=>{$('#rag-send').disabled=!e.target.checked||!p.configured;};$('#rag-send').onclick=send;status('请核对发送范围；未确认不会调用外部模型。');
  }catch(err){status(err.message);}finally{if(token===epoch)setBusy(false);}
 };
 async function send(){
  if(!pending||busy||!$('#rag-allow').checked)return;const p=pending,token=++epoch;pending=null;setBusy(true);$('#rag-consent').innerHTML='';status('正在请求参考回答；请勿重复发送，真实API可能计费。');
  try{const result=await api('/api/rag/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket:p.ticket,consent:true})});if(token!==epoch)return;
   turns.push({...result,question:p.question});draw();$('#rag-question').value='';status('参考回答已返回，请核对引用。');
  }catch(e){if(token===epoch)status(e.message+' 请重新准备并确认后重试。');}finally{if(token===epoch)setBusy(false);}
 }
 $('#rag-chat').onclick=e=>{const cite=e.target.closest('[data-rag-cite]'),basis=e.target.closest('[data-rag-basis]');if(cite)openSources([turns[Number(cite.dataset.ragCite)].citations[Number(cite.dataset.source)]]);if(basis)openSources(turns[Number(basis.dataset.ragBasis)].evidence);};
 $('#rag-clear').onclick=()=>{epoch++;session=null;pending=null;turns=[];draw();$('#rag-consent').innerHTML='';status('当前会话已清空；刷新页面也会清空。');};
 return {show(){onShow();health();},hide(){if($('#rag-modal').open)close();$('#rag-view').hidden=true;$('#nav-rag').classList.remove('active');}};
}};
