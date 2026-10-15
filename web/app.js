if (window.location.protocol === 'file:') {
  document.body.innerHTML = `<section class="opening-help"><span class="brand-mark">P18</span><h1>请通过工作台入口打开</h1><p>你现在打开的是网页源文件。上传、解析和文档列表需要本机服务，无法通过双击 index.html 使用。</p><ol><li>在项目文件夹里双击 <strong>启动文档工作台.command</strong>。</li><li>等待浏览器自动打开，之后就可以上传和查看文档。</li></ol><a class="primary" href="http://127.0.0.1:8765/">服务已启动？打开文档工作台 →</a><p class="subtitle">若链接无法连接，请先运行启动文件。本工作台只在你的电脑上运行。</p></section>`;
} else {
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const states = {queued:'等待处理',converting:'转换与解析中',parsing:'解析与检查中',review:'等待复核',held:'暂不入库',ready:'待接入知识库',failed:'处理失败',deleting:'删除中',delete_failed:'删除未完成'};
const qualities = {pending:'等待检查',clear:'未发现明显异常',review:'需要复核',failed:'处理失败'};
const busyStates = new Set(['queued','converting','parsing']);
let records = [], selected = [], current = null, page = 1, previewPages = 0, onlyReview = false, uploadBusy = false;
let toastTimer, detailRequest = 0, previewRequest = 0;
const size = n => n < 1e6 ? `${(n / 1000).toFixed(1)} KB` : `${(n / 1e6).toFixed(1)} MB`;
const date = value => new Date(value).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
function toast(text) { $('#toast').textContent = text; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 4500); }
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{'X-P18-Client':'workbench',...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求未完成，请刷新后重试。');
  return data;
}
function badge(doc) {return `<span class="badge ${doc.state==='failed'||doc.state==='delete_failed'?'failed':doc.state==='review'||doc.state==='held'?'review':busyStates.has(doc.state)?'processing':'ready'}">${esc(states[doc.state]||doc.state)}</span>`;}
function qualityBadge(doc) {return `<span class="badge ${esc(doc.quality)}">${esc(qualities[doc.quality]||'待检查')}${doc.issues_count ? ` · ${doc.issues_count} 项` : ''}</span>`;}

function renderList() {
  const q = $('#search').value.trim().toLocaleLowerCase(), state = $('#state-filter').value, quality = $('#quality-filter').value;
  const filtered = records.filter(d => d.name.toLocaleLowerCase().includes(q) && (!state || (state==='processing'?busyStates.has(d.state):d.state===state)) && (!quality || d.quality===quality) && (!onlyReview || d.quality==='review'));
  $('#nav-count').textContent=records.length; $('#stat-total').textContent=records.length;
  $('#stat-processing').textContent=records.filter(d=>busyStates.has(d.state)).length;
  $('#stat-review').textContent=records.filter(d=>['review','held'].includes(d.state)).length;
  $('#stat-ready').textContent=records.filter(d=>d.state==='ready').length;
  $('#file-count').textContent=`${records.length} 份`;
  $('#documents').innerHTML=filtered.map(d=>`<tr><td><div class="file-cell"><span class="file-icon ${d.ext!=='.pdf'?'word':''}">${esc(d.ext.slice(1).toUpperCase())}</span><div><button class="file-title" data-open="${d.id}">${esc(d.name)}</button><div class="file-sub">${size(d.size)}${d.characters?` · ${d.characters.toLocaleString()} 字符`:''}${d.replaces?' · 替换文件':''}</div></div></div></td><td class="timestamp">${date(d.created_at)}</td><td>${badge(d)}</td><td>${qualityBadge(d)}</td><td><div class="row-actions">${d.state!=='delete_failed'?`<button data-open="${d.id}">${d.state==='review'?'去复核':'查看'}</button>`:''}${d.state==='failed'?`<button data-retry="${d.id}">重试</button>`:''}<button class="danger" data-delete="${d.id}">${d.state==='delete_failed'?'重试删除':'删除'}</button></div></td></tr>`).join('');
  $('#empty').hidden=filtered.length>0;
  $('#empty h3').textContent=records.length?'没有匹配的文档':'从第一份文档开始';
  $('#empty p').innerHTML=records.length?'试试更换搜索词或筛选条件。':'支持文字型 PDF、DOCX 和旧版 DOC。<br>没有企业资料也可以先使用虚构样例体验完整流程。';
  $('#empty-upload').hidden=records.length>0;
  $('#list-summary').textContent=`显示 ${filtered.length} / ${records.length} 份文档`;
}
async function refresh() {
  try {
    records=await api('/api/documents'); $('#list-error').hidden=true; renderList();
    if(current) {
      const latest=records.find(d=>d.id===current.id);
      if(!latest) return back();
      if(latest.updated_at!==current.updated_at) await openDetail(current.id, true);
    }
  } catch(error) {$('#list-error').textContent=error.message;$('#list-error').hidden=false;}
}
function back() {current=null;detailRequest++;previewRequest++;$('#list-view').hidden=false;$('#detail-view').hidden=true;}
function extractedHTML(result) {
  if(!result?.blocks?.length) return '<p class="pane-empty">暂无提取内容。处理完成后会显示实际结果。</p>';
  return result.blocks.map(b=>`<article class="extracted-block" data-block="${esc(b.id)}"><h3>${esc(b.label)}</h3>${b.kind!=='table'?`<pre>${esc(b.text || '本页未提取到文字。')}</pre>`:''}${(b.tables||[]).map(t=>`<table aria-label="提取的表格"><tbody>${t.rows.map(row=>`<tr>${row.map(cell=>`<td>${esc(cell ?? '〔空或合并单元格〕')}</td>`).join('')}</tr>`).join('')}</tbody></table>`).join('')}</article>`).join('');
}
async function openDetail(id, preserve=false) {
  const request=++detailRequest;
  try {
    const doc=await api(`/api/documents/${id}`);
    if(request!==detailRequest) return;
    current=doc;if(!preserve)page=1;
    $('#list-view').hidden=true;$('#detail-view').hidden=false;
    $('#detail-name').textContent=doc.name;
    $('#detail-meta').textContent=`${doc.ext.slice(1).toUpperCase()} · ${size(doc.size)} · 上传于 ${date(doc.created_at)} · 第 ${doc.revision} 次解析`;
    let statusText=doc.error || (doc.state==='ready'?'解析资料已备好；知识库尚未接通，当前不可检索。':doc.state==='review'?'检测到需复核内容。请查看问题位置，再决定是否使用已提取内容。':doc.state==='held'?'你选择了暂不入库。原文件与提取内容已保留，可继续核对。':'正在本机处理，请稍候；无需保持上传窗口打开。');
    $('#detail-status').innerHTML=`<div>${badge(doc)} ${qualityBadge(doc)}<strong>${esc(statusText)}</strong>${doc.quality==='review'?'<span>部分内容未解析或结构待核对；确认使用不会消除风险标识。</span>':''}${doc.state==='failed'?`<button class="text-button" data-retry="${doc.id}">重新处理</button>`:''}</div>`;
    $('#preview-warnings').innerHTML=(doc.result?.preview_warnings||[]).map(t=>`<div class="preview-warning">${esc(t)}</div>`).join('');
    const issues=doc.result?.issues||[];
    $('#issue-count').textContent=`${issues.length} 项`;
    $('#issues').innerHTML=issues.length?issues.map((it,i)=>`<button class="issue-item" data-issue="${i}"><strong>${it.page?`第 ${it.page} 页`:it.block?'正文 / 表格位置':'文档级提示'}</strong>${esc(it.message)}<span class="link-label">${it.page?'查看对应原文页 →':it.block?'定位提取内容 →':'核对整份文档'}</span></button>`).join(''):`<p class="subtitle">${doc.quality==='clear'?'自动检查未发现明显异常，仍建议抽查内容。':'尚无可定位的问题，请查看处理提示。'}</p>`;
    $('#review-actions').hidden=!['review','held'].includes(doc.state);
    $('#text-count').textContent=`${(doc.characters||0).toLocaleString()} 字符`;
    const labels={uploaded:'文件已上传',extraction_finished:'解析检查完成',review_accept:'已确认使用当前提取内容',review_hold:'选择暂不入库',retry:'重新处理',replacement_prepared:'替换资料已备好'};
    $('#review-history').innerHTML='<strong>处理记录</strong>'+(doc.events||[]).map(e=>`<div class="history-item">${esc(labels[e.action]||e.action)}<br>${date(e.at)} · 解析 ${e.revision}</div>`).join('');
    for (const select of [$('#left-kind'),$('#right-kind')]) {
      const option=select.querySelector('[value="converted"]');option.disabled=!doc.result?.converted;
      if(!preserve)select.value=select.id==='left-kind'?'original':'extracted';
      else if(select.value==='converted'&&!doc.result?.converted)select.value='original';
    }
    await renderPanes();
  } catch(error){toast(error.message);}
}
async function renderPanes() {
  if(!current)return;
  const doc=current, request=++previewRequest;
  const left=$('#left-kind').value,right=$('#right-kind').value;
  let maxPages=0;
  await Promise.all([['left',left],['right',right]].map(async([side,kind])=>{
    const container=$(`#${side}-content`);
    if(kind==='extracted'){container.innerHTML=extractedHTML(doc.result);return;}
    container.innerHTML='<p class="pane-empty">正在加载预览…</p>';
    try {
      const meta=await api(`/api/documents/${doc.id}/preview/${kind}/meta`);
      if(request!==previewRequest)return;
      maxPages=Math.max(maxPages,meta.pages);
      const p=Math.min(page,meta.pages);
      container.innerHTML=`<img src="/api/documents/${doc.id}/preview/${kind}/${p}?revision=${doc.revision}" alt="${esc(doc.name)} ${kind==='converted'?'转换副本':'原文件'}预览，第 ${p} 页">`;
    } catch(error) {if(request===previewRequest)container.innerHTML=`<p class="pane-empty">${esc(error.message)}</p>`;}
  }));
  if(request!==previewRequest)return;
  previewPages=maxPages;
  $('#page-label').textContent=maxPages?`第 ${Math.min(page,maxPages)} / ${maxPages} 页`:'暂无预览页';
  $('#page-prev').disabled=page<=1;$('#page-next').disabled=page>=maxPages;
  $('#preview-note').textContent=doc.ext==='.pdf'?'页码按原 PDF 物理页序计算，可能与印刷页码不同。':'Word 预览由转换生成，排版可能变化；不能据此保证原始排版一致。问题按段落或表格定位。';
  const download=$('#left-download');download.hidden=left==='extracted';download.href=`/api/documents/${doc.id}/file/${left}`;
}
function focusIssue(index) {
  const it=current?.result?.issues[index];if(!it)return;
  if(it.page){page=it.page;$('#left-kind').value='original';}
  $('#right-kind').value='extracted';
  renderPanes().then(()=>{
    const id=it.block||(it.page?`page-${it.page}`:null);
    if(id){const target=$('#right-content').querySelector(`[data-block="${CSS.escape(id)}"]`);if(target){target.classList.add('focused');target.scrollIntoView({block:'nearest'});}}
  });
}
function ask(title, body, action='确认') {
  const dialog=$('#confirm-dialog');$('#confirm-title').textContent=title;$('#confirm-body').textContent=body;$('#confirm-ok').textContent=action;
  return new Promise(resolve=>{
    const done=value=>{dialog.close();$('#confirm-ok').onclick=null;$('#confirm-cancel').onclick=null;dialog.oncancel=null;resolve(value);};
    $('#confirm-ok').onclick=()=>done(true);$('#confirm-cancel').onclick=()=>done(false);dialog.oncancel=e=>{e.preventDefault();done(false);};dialog.showModal();
  });
}
async function removeDoc(id) {
  if(!await ask('删除这份文档？','将删除原文件、转换副本、提取结果及关联数据。之后的新检索不得使用该文档。当前知识库尚未接通。','确认删除'))return;
  try{await api(`/api/documents/${id}`,{method:'DELETE'});if(current?.id===id)back();await refresh();toast('文档及处理副本已删除。');}catch(e){toast(e.message);await refresh();}
}
async function retryDoc(id){try{await api(`/api/documents/${id}/retry`,{method:'POST'});await refresh();toast('已加入处理队列。');}catch(e){toast(e.message);}}
async function reviewDoc(action){
  if(!current)return;
  if(action==='accept'&&!await ask('确认使用已提取内容？','当前结果可能存在遗漏或结构问题。确认后资料将备好，等待后续知识库接入；风险标识仍会保留。','确认使用'))return;
  try{await api(`/api/documents/${current.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,revision:current.revision})});await refresh();toast(action==='accept'?'已记录复核确认；风险提示仍保留。':'已暂缓入库。');}catch(e){toast(e.message);}
}
function openUpload(){if(!uploadBusy){selected=[];$('#file-input').value='';$('#upload-results').innerHTML='';renderSelected();}$('#upload-dialog').showModal();}
function chooseFiles(files){if(uploadBusy)return;selected=Array.from(files);$('#upload-results').innerHTML='';renderSelected();}
function renderSelected(){
  const total=selected.reduce((sum,f)=>sum+f.size,0);
  $('#selected-files').innerHTML=selected.map(f=>`<div class="selected-file"><span>${esc(f.name)}</span><span>${size(f.size)}</span></div>`).join('');
  let error=selected.length>20?'单批最多 20 个文件':total>100e6?'单批总大小不能超过 100 MB':selected.some(f=>f.size>20e6)?'单个文件不能超过 20 MB':selected.some(f=>!f.size)?'不能上传空文件':selected.some(f=>!(/\.(pdf|docx|doc)$/i.test(f.name)))?'仅支持 PDF、DOCX 和 DOC':'';
  $('#selection-summary').textContent=error||`${selected.length} 份文档 · ${size(total)}`;
  $('#upload-submit').disabled=!selected.length||!!error||uploadBusy;
}
async function sendFiles(files,mode='ask',replaceId=''){
  const form=new FormData();files.forEach(f=>form.append('files',f));form.append('mode',mode);form.append('replace_id',replaceId);
  return api('/api/documents',{method:'POST',body:form});
}
function showResult(result, files, replaceElement=null){
  const el=document.createElement('div');el.className=`result-item ${result.status==='rejected'?'error':''}`;
  el.innerHTML=`<strong>${esc(result.name)}</strong><br>${esc(result.message||'上传成功，已加入处理队列。')}`;
  if(result.status==='conflict'){
    const choices=document.createElement('div');choices.className='conflict-choices';
    choices.innerHTML=`<button data-choice="keep">作为另一份保存</button><select aria-label="选择替换目标">${result.candidates.map(d=>`<option value="${d.id}">${esc(d.name)} · ${date(d.created_at)}</option>`).join('')}</select><button data-choice="replace">替换选中文档</button>`;
    choices.addEventListener('click',async e=>{
      const button=e.target.closest('[data-choice]');if(!button)return;
      const file=files.find(f=>f.name===result.name);if(!file)return toast('请重新选择文件。');
      if(button.dataset.choice==='replace'&&!await ask('替换已有文档？','新文件完成处理及必要复核后才替换旧资料；新文件失败时旧资料仍保留。','开始替换'))return;
      choices.querySelectorAll('button').forEach(b=>b.disabled=true);
      try{const results=await sendFiles([file],button.dataset.choice,choices.querySelector('select').value);showResult(results[0],files,el);await refresh();}catch(err){toast(err.message);choices.querySelectorAll('button').forEach(b=>b.disabled=false);}
    });el.append(choices);
  }else if(result.id){const button=document.createElement('button');button.textContent='查看文档 →';button.onclick=()=>{$('#upload-dialog').close();openDetail(result.id);};el.append(document.createElement('br'),button);}
  if(replaceElement)replaceElement.replaceWith(el);else $('#upload-results').append(el);
}
async function submitUpload(){
  if(uploadBusy||!selected.length)return;uploadBusy=true;renderSelected();$('#upload-submit').textContent='正在上传…';
  try{const files=[...selected],results=await sendFiles(files);$('#upload-results').innerHTML='';results.forEach(r=>showResult(r,files));selected=[];await refresh();}catch(e){$('#upload-results').innerHTML=`<div class="result-item error">${esc(e.message)}</div>`;}
  finally{uploadBusy=false;$('#upload-submit').textContent='开始上传';renderSelected();}
}
$('#search').addEventListener('input',renderList);$('#state-filter').onchange=renderList;$('#quality-filter').onchange=renderList;
$('#review-only').onclick=()=>{onlyReview=!onlyReview;$('#review-only').setAttribute('aria-pressed',onlyReview);renderList();};
$('#refresh').onclick=refresh;$('#back').onclick=back;$('#nav-documents').onclick=back;
$('#upload-open').onclick=openUpload;$('#empty-upload').onclick=openUpload;$('#file-input').onchange=e=>chooseFiles(e.target.files);$('#upload-submit').onclick=submitUpload;
$('#dropzone').ondragover=e=>{e.preventDefault();$('#dropzone').classList.add('dragover');};$('#dropzone').ondragleave=()=>$('#dropzone').classList.remove('dragover');$('#dropzone').ondrop=e=>{e.preventDefault();$('#dropzone').classList.remove('dragover');chooseFiles(e.dataTransfer.files);};
$('#upload-dialog').addEventListener('cancel',e=>{if(uploadBusy)e.preventDefault();});
$('#detail-delete').onclick=()=>current&&removeDoc(current.id);$('#accept').onclick=()=>reviewDoc('accept');$('#hold').onclick=()=>reviewDoc('hold');
$('#left-kind').onchange=renderPanes;$('#right-kind').onchange=renderPanes;$('#page-prev').onclick=()=>{if(page>1){page--;renderPanes();}};$('#page-next').onclick=()=>{if(page<previewPages){page++;renderPanes();}};
document.addEventListener('click',e=>{const button=e.target.closest('[data-open],[data-delete],[data-retry],[data-issue]');if(!button)return;if(button.dataset.open)openDetail(button.dataset.open);else if(button.dataset.delete)removeDoc(button.dataset.delete);else if(button.dataset.retry)retryDoc(button.dataset.retry);else focusIssue(Number(button.dataset.issue));});
refresh();setInterval(refresh,2500);
}
