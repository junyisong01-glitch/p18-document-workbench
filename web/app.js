let ragUI=null;
if (window.location.protocol === 'file:') {
  document.body.innerHTML = `<section class="opening-help"><span class="brand-mark">P18</span><h1>请通过工作台入口打开</h1><p>你现在打开的是网页源文件。上传、解析和文档列表需要本机服务，无法通过双击 index.html 使用。</p><ol><li>在项目文件夹里双击 <strong>启动文档工作台.command</strong>。</li><li>等待浏览器自动打开，之后就可以上传和查看文档。</li></ol><a class="primary" href="http://127.0.0.1:8765/">服务已启动？打开文档工作台 →</a><p class="subtitle">若链接无法连接，请先运行启动文件。本工作台只在你的电脑上运行。</p></section>`;
} else {
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const states = {queued:'等待处理',converting:'转换与解析中',parsing:'解析与检查中',review:'等待复核',held:'暂不入库',ready:'待构建',failed:'处理失败',deleting:'删除中',delete_failed:'删除未完成'};
const qualities = {pending:'等待检查',clear:'未发现明显异常',review:'需要复核',failed:'处理失败'};
const busyStates = new Set(['queued','converting','parsing']);
let records = [], selected = [], current = null, page = 1, previewPages = 0, onlyReview = false, uploadBusy = false;
let toastTimer, detailRequest = 0, previewRequest = 0, searchUI=null, semanticHealth=null, refreshing=false;
const size = n => n < 1e6 ? `${(n / 1000).toFixed(1)} KB` : `${(n / 1e6).toFixed(1)} MB`;
const date = value => new Date(value).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
function toast(text) { $('#toast').textContent = text; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 4500); }
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{'X-P18-Client':'workbench',...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) {const error=new Error(typeof data.detail==='string'?data.detail:data.detail?.message||'请求未完成，请核对输入或稍后重试。');error.code=data.detail?.code;throw error;}
  return data;
}
function badge(doc) {if(doc.state==='ready'){const index=doc.index||{status:'unavailable',searchable:false};return `<span class="badge ${index?.status==='failed'?'failed':index?.searchable?'ready':'processing'}">${esc(window.P18Search?.indexLabel(index)||'待建立索引')}</span>`;}return `<span class="badge ${doc.state==='failed'||doc.state==='delete_failed'?'failed':doc.state==='review'||doc.state==='held'?'review':busyStates.has(doc.state)?'processing':'ready'}">${esc(states[doc.state]||doc.state)}</span>`;}
function qualityBadge(doc) {if(doc.review_completed)return `<span class="badge ${doc.admission?.incomplete?'review':'ready'}">已复核${doc.admission?.incomplete?' · 内容不完整':''}</span>`;return `<span class="badge ${esc(doc.quality)}">${esc(qualities[doc.quality]||'待检查')}${doc.issues_count ? ` · ${doc.issues_count} 项` : ''}</span>`;}

function renderList() {
  const q = $('#search').value.trim().toLocaleLowerCase(), state = $('#state-filter').value, quality = $('#quality-filter').value;
  const filtered = records.filter(d => d.name.toLocaleLowerCase().includes(q) && (!state || (state==='processing'?busyStates.has(d.state):d.state===state)) && (!quality || d.quality===quality) && (!onlyReview || d.review_pending));
  $('#nav-count').textContent=records.length; $('#stat-total').textContent=records.length;
  $('#stat-processing').textContent=records.filter(d=>busyStates.has(d.state)).length;
  $('#stat-review').textContent=records.filter(d=>d.review_pending).length;
  $('#stat-ready').textContent=records.filter(d=>d.index?.searchable===true).length;
  $('#file-count').textContent=`${records.length} 份`;
  $('#documents').innerHTML=filtered.map(d=>`<tr><td><div class="file-cell"><span class="file-icon ${d.ext!=='.pdf'?'word':''}">${esc(d.ext.slice(1).toUpperCase())}</span><div><button class="file-title" data-open="${d.id}">${esc(d.name)}</button><div class="file-sub">${size(d.size)}${d.characters?` · ${d.characters.toLocaleString()} 字符`:''}${d.replaces?' · 替换文件':''}</div></div></div></td><td class="timestamp">${date(d.created_at)}</td><td>${badge(d)}</td><td>${qualityBadge(d)}</td><td><div class="row-actions">${d.state!=='delete_failed'?`<button data-open="${d.id}">${d.state==='review'?'去复核':'查看'}</button>`:''}${d.state==='failed'?`<button data-retry="${d.id}">重试</button>`:''}${canIndexRetry(d)?`<button data-index-retry="${d.id}">${d.index.status==='failed'?'重试索引':'建立索引'}</button>`:''}<button class="danger" data-delete="${d.id}">${d.state==='delete_failed'?'重试删除':'删除'}</button></div></td></tr>`).join('');
  $('#empty').hidden=filtered.length>0;
  $('#empty h3').textContent=records.length?'没有匹配的文档':'从第一份文档开始';
  $('#empty p').innerHTML=records.length?'试试更换搜索词或筛选条件。':'支持文字型 PDF、DOCX 和旧版 DOC。<br>没有企业资料也可以先使用虚构样例体验完整流程。';
  $('#empty-upload').hidden=records.length>0;
  $('#list-summary').textContent=`显示 ${filtered.length} / ${records.length} 份文档`;
}
async function refresh() {
  if(refreshing)return;refreshing=true;
  try {
    const [docs,health]=await Promise.all([api('/api/documents'),api('/api/semantic').catch(()=>({enabled:false,error:'当前服务版本较旧，未提供语义能力接口；需要先安全重启，文档管理仍可使用。'}))]);
    records=docs;semanticHealth=health;$('#list-error').hidden=true;renderList();
    $('#library-service-note').textContent=health.enabled?'符合入库条件后自动切分并建立本地索引；只有索引有效才可检索。请在知识检索中核对片段与原文。':(typeof health.error==='string'?health.error:health.error?.message)||(!health.setup?.ready?health.setup?.message:'本地语义检索尚未启用；文档管理可继续使用。请通过原启动入口检查和启用。');
    searchUI?.sync(records,semanticHealth);
    if(current) {
      const latest=records.find(d=>d.id===current.id);
      if(!latest) return back();
      if(latest.updated_at!==current.updated_at) await openDetail(current.id, true);
      else if(indexSignature(latest.index)!==indexSignature(current.index)) await openDetail(current.id,true);
      else if([$('#left-kind').value,$('#right-kind').value].includes('chunks') && document.querySelector('.chunk-summary')?.textContent.match(/等待切分|正在切分/)) await renderPanes();
    }
  } catch(error) {$('#list-error').textContent=error.message;$('#list-error').hidden=false;searchUI?.offline('暂时无法连接本机服务，请检查原工作台是否仍在运行。');}
  finally {refreshing=false;}
}
function back() {ragUI?.hide();current=null;detailRequest++;previewRequest++;searchUI?.hide();$('#search-view').hidden=true;$('#nav-search').classList.remove('active');$('#nav-documents').classList.add('active');$('#current-page').textContent='文档管理';$('#list-view').hidden=false;$('#detail-view').hidden=true;}
function indexSignature(index){return JSON.stringify(['status','token','generation','updated_at','searchable','error'].map(key=>index?.[key]));}
function canIndexRetry(doc){return doc.admission?.eligible && semanticHealth?.enabled && ['failed','stale','not_started'].includes(doc.index?.status);}
async function retryIndex(id){const doc=records.find(d=>d.id===id)||current;if(!doc)return;try{await api(`/api/documents/${id}/index`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:doc.revision})});toast('已请求建立当前版本索引，请留意真实状态。');await refresh();}catch(e){toast(e.message);}}

let previewZoom=1;
function previewLink(item) {
  const n=item.preview_pages?.original;
  return n?`<button class="text-button" data-preview-page="${n}">查看系统转换预览第 ${n} 页</button>`:'<small>暂无法确定对应预览页</small>';
}
function tableHTML(t) {
  if(!t.cells)return `<table><tbody>${t.rows.map(row=>`<tr>${row.map(c=>`<td>${esc(c??'〔空或合并单元格〕')}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  return `<div class="table-scroll"><table><tbody>${t.rows.map((row,i)=>`<tr>${row.map((value,j)=>{
    const cell=t.cells.find(c=>c.row===i+1&&c.column===j+1);
    if(cell)return `<td rowspan="${cell.rowspan}" colspan="${cell.colspan}"><div>${esc(cell.text)}</div><small>第 ${cell.row} 行 · 第 ${cell.column} 列</small>${cell.text.trim()?previewLink(cell):''}</td>`;
    return value===null?'':'<td></td>';
  }).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function extractedHTML(result) {
  if(!result?.blocks?.length) return '<p class="pane-empty">暂无提取内容。</p>';
  return result.blocks.filter(b=>b.kind!=='paragraph'||b.text?.trim()||b.has_objects).map(b=>`<article class="extracted-block" data-block="${esc(b.id)}"><h3>${esc(b.label)}</h3>${b.kind!=='page'?previewLink(b):''}${b.kind!=='table'?`<pre>${esc(b.text || (b.kind==='page'?'本页未提取到文字。':'含图片或未支持对象，未提取到正文，请核对原文件。'))}</pre>`:''}${(b.tables||[]).map(tableHTML).join('')}</article>`).join('');
}
function chunksHTML(result) {
  const labels={not_started:'尚未切分',blocked:'未通过入库条件',queued:'等待切分',processing:'正在切分',complete:'切分完成',failed:'切分失败',stale:'配置或结果已变化'};
  const cfg=result.config||result.current_config;
  const configText=cfg?`目标 ${cfg.target_chars} 字符 · 重叠参考 ${cfg.overlap_chars} 字符 · ${cfg.method}`:'配置不可用';
  return `<div class="chunk-summary"><h3>${esc(labels[result.status]||result.status)} · ${result.count||0} 个片段</h3><p>${esc(result.message)}</p><p>${esc(configText)}</p><p>长度是测试初值，特殊结构可超过目标；切分完成不等于可检索，请查看文档索引状态。</p>${result.status==='stale'?`<p>当前配置：${esc(JSON.stringify(result.current_config))}；旧配置片段不予使用。</p>`:''}${result.error?`<p class="error-banner">${esc(result.error)}</p>`:''}${['not_started','stale','failed'].includes(result.status)?'<button class="secondary" data-generate-chunks>重新生成切分结果</button>':''}${(result.warnings||[]).map(w=>`<p class="preview-warning">${esc(w)}</p>`).join('')}</div>`+(result.chunks||[]).map(c=>`<article class="extracted-block chunk-block"><h3>片段 ${c.order} · ${esc(c.section||'正文')}</h3><p class="subtitle">${esc({text:'正文',heading:'标题',table:'表格',code:'代码 / 接口',steps:'操作步骤',pdf_page:'PDF 整页保守保留'}[c.kind]||c.kind)} · 解析 ${c.revision}${c.row_start?` · 提取表格行 ${c.row_start}–${c.row_end}（重复首行作上下文）`:''}</p>${c.risk?.incomplete?'<p class="preview-warning">来源文档部分内容未解析，复核后风险仍保留。</p>':''}${c.risk?.quality==='review'?'<p class="subtitle">来源含检查提示，已按当前版本完成必要复核；请结合原文查看。</p>':''}${c.table_title?`<p>表格上下文：${esc(c.table_title)}</p>`:''}<pre>${esc(c.text)}</pre><div class="chunk-sources">${(c.sources||[]).map(src=>`<button class="text-button" ${src.page?`data-chunk-page="${src.page}"`:src.block_id?`data-chunk-block="${esc(src.block_id)}"`:''}>${esc(src.label||'文档级来源')}${src.page?' · 查看原 PDF 页':src.block_id?' · 定位原始提取位置':''}</button>`).join('')}</div><details><summary>片段标识与实际配置</summary><p>${esc(c.id)}</p><pre>${esc(JSON.stringify(c.config,null,2))}</pre></details></article>`).join('');
}
async function generateChunks(){
  if(!current)return;
  try{await api(`/api/documents/${current.id}/chunks`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.revision})});await renderPanes();}catch(error){toast(error.message);}
}
async function locateChunkSource(button){
  if(!current)return;
  const block=button.dataset.chunkBlock;
  $('#right-kind').value='chunks';
  if(button.dataset.chunkPage){page=Number(button.dataset.chunkPage);$('#left-kind').value='original';}
  else if(block){$('#left-kind').value='extracted';}
  await renderPanes();
  if(block){const target=$('#left-content').querySelector(`[data-block="${CSS.escape(block)}"]`);if(target){target.classList.add('focused');target.scrollIntoView({block:'nearest'});}}
}

async function openDetail(id, preserve=false) {
  const request=++detailRequest;
  try {
    const doc=await api(`/api/documents/${id}`);
    if(request!==detailRequest) return;
    const resetReview=!preserve || current?.revision!==doc.revision;
    ragUI?.hide();current=doc;if(!preserve)page=1;searchUI?.hide();$('#search-view').hidden=true;$('#nav-search').classList.remove('active');$('#nav-documents').classList.add('active');$('#current-page').textContent='文档管理';
    if(resetReview){$('#reviewer').value='';$('#review-note').value='';}
    $('#list-view').hidden=true;$('#detail-view').hidden=false;
    $('#detail-name').textContent=doc.name;
    $('#detail-meta').textContent=`${doc.ext.slice(1).toUpperCase()} · ${size(doc.size)} · 上传于 ${date(doc.created_at)} · 第 ${doc.revision} 次解析`;
    let statusText=doc.error || (doc.state==='ready'?(doc.index?.message || '待建立有效索引。'):doc.state==='review'?'检测到需复核内容。请查看问题位置，再决定是否使用已提取内容。':doc.state==='held'?'你选择了暂不入库。原文件与提取内容已保留，可继续核对。':'正在本机处理，请稍候；无需保持上传窗口打开。');
    $('#detail-status').innerHTML=`<div>${badge(doc)} ${qualityBadge(doc)}<strong>${esc(statusText)}</strong>${doc.admission?.incomplete?'<span>部分内容未解析，复核后仍保留内容不完整风险。</span>':doc.review_completed?'<span>已完成复核，原检查提示和审核记录保留供查阅。</span>':doc.quality==='review'?'<span>请核对检查提示后记录复核结论。</span>':''}${doc.state==='failed'?`<button class="text-button" data-retry="${doc.id}">重新处理</button>`:''}${canIndexRetry(doc)?`<button class="text-button" data-index-retry="${doc.id}">${doc.index.status==='failed'?'重试索引':'建立索引'}</button>`:''}${doc.index?.error?`<span>${esc(doc.index.error)}</span>`:''}</div>`;
    $('#preview-warnings').innerHTML=(doc.result?.preview_warnings||[]).map(t=>`<div class="preview-warning">${esc(t)}</div>`).join('');
    const issues=doc.result?.issues||[];
    $('#issue-count').textContent=`${issues.length} 项`;
    $('#issues').innerHTML=issues.length?issues.map((it,i)=>`<button class="issue-item" data-issue="${i}"><strong>${it.page?`第 ${it.page} 页`:it.block?'正文 / 表格位置':'文档级提示'}</strong>${esc(it.message)}<span class="link-label">${it.page?'查看对应原文页 →':it.block?'定位提取内容 →':'核对整份文档'}</span></button>`).join(''):`<p class="subtitle">${doc.quality==='clear'?'自动检查未发现明显异常，仍建议抽查内容。':'尚无可定位的问题，请查看处理提示。'}</p>`;
    $('#admission-summary').innerHTML=`<strong>入库条件检查</strong><p>${esc(doc.admission?.eligible?'已满足入库条件；是否可检索取决于当前索引状态。':'尚未满足入库条件，需完成解析或必要复核。')}</p>${(doc.admission?.categories||[]).map(c=>`<p class="badge review">${esc(c.label)}</p>`).join('')}${doc.admission?.incomplete?'<p>部分内容未解析；后续检索与问答仍须保留风险提示。</p>':''}${doc.review_decision?`<p>最近复核：${esc({accepted:'确认内容可用',incorrect:'确认有误，暂不入库',uncertain:'无法判断，暂不入库'}[doc.review_decision.outcome])}</p>`:''}`;
    $('#review-checks').innerHTML=(doc.admission?.requirements||[]).map(r=>`<label style="display:block;margin:12px 0"><input type="checkbox" data-review-check="${esc(r.key)}"> ${esc(r.label)}</label>`).join('');
    $('#accept').textContent=doc.admission?.incomplete?'确认使用已提取内容':'确认内容可用';
    $('#accept').disabled=(doc.admission?.categories||[]).some(c=>c.code==='unusable');
    $('#review-actions').hidden=!['review','held'].includes(doc.state);
    $('#text-count').textContent=`${(doc.characters||0).toLocaleString()} 字符`;
    const labels={uploaded:'文件已上传',extraction_finished:'解析检查完成',review_accept:'已确认使用当前提取内容',review_hold:'选择暂不入库',retry:'重新处理',replacement_prepared:'替换资料已备好',admission_review_required:'入库规则更新，需按异常类别补充复核'};
    $('#review-history').innerHTML=`<strong>处理与审核记录 · ${(doc.events||[]).filter(e=>e.action.startsWith('review_')).length} 次审核</strong>`+(doc.events||[]).map(e=>{
      const r=e.payload, isReview=e.action.startsWith('review_');
      return `<div class="history-item">${esc(labels[e.action]||e.action)}<br>${date(e.at)} · 解析 ${e.revision}${isReview?`<br>审核人：${esc(r?.reviewer||'未记录')}${r?.reviewer?'（人工填写，身份未验证）':''}<br>结论：${esc(r?{accepted:'确认内容可用',incorrect:'确认有误，暂不入库',uncertain:'无法判断，暂不入库'}[r.outcome]:e.action==='review_accept'?'确认使用':'暂不入库')}<br>文件：${esc(r?.document_name||doc.name)}${r?`<br>核对项：${(r.requirements||[]).map(q=>`${r.checks?.[q.key]?'已确认':'未确认'}：${esc(q.label)}`).join('；')||'无'}<br>问题：${[...(r.issues||[]).map(i=>`${i.page?'第 '+i.page+' 页':i.block||'文档级'}：${i.message||i.kind}`),...(r.preview_warnings||[])].map(esc).join('；')||'无'}<br>备注：${esc(r.note||'未填写')}`:'<br>旧记录未保存详细审核信息'}`:''}</div>`;
    }).join('');
    for (const select of [$('#left-kind'),$('#right-kind')]) {
      select.querySelector('[value="original"]').textContent=doc.ext==='.pdf'?'原文件预览':'Word 转换预览';
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
  const chunkPromise=[left,right].includes('chunks')?api(`/api/documents/${doc.id}/chunks`):null;
  await Promise.all([['left',left],['right',right]].map(async([side,kind])=>{
    const container=$(`#${side}-content`);
    if(kind==='chunks'){
      try{const result=await chunkPromise;if(request===previewRequest)container.innerHTML=chunksHTML(result);}catch(error){if(request===previewRequest)container.innerHTML=`<p class="pane-empty">${esc(error.message)}</p>`;}
      return;
    }
    if(kind==='extracted'){container.innerHTML=extractedHTML(doc.result);return;}
    container.innerHTML='<p class="pane-empty">正在加载预览…</p>';
    try {
      const meta=await api(`/api/documents/${doc.id}/preview/${kind}/meta`);
      if(request!==previewRequest)return;
      maxPages=Math.max(maxPages,meta.pages);
      const p=Math.min(page,meta.pages);
      container.innerHTML=`<img style="width:${previewZoom*100}%;max-width:none" src="/api/documents/${doc.id}/preview/${kind}/${p}?revision=${doc.revision}&zoom=${previewZoom}" alt="${esc(doc.name)} ${kind==='converted'?'转换副本预览':doc.ext==='.pdf'?'原文件预览':'Word 转换预览'}，第 ${p} 页">`;
    } catch(error) {if(request===previewRequest)container.innerHTML=`<p class="pane-empty">${esc(error.message)}</p>`;}
  }));
  if(request!==previewRequest)return;
  previewPages=maxPages;
  $('#page-label').textContent=maxPages?`第 ${Math.min(page,maxPages)} / ${maxPages} 页`:'暂无预览页';
  $('#page-prev').disabled=page<=1;$('#page-next').disabled=page>=maxPages;
  $('#preview-note').textContent=doc.ext==='.pdf'?'页码按原 PDF 物理页序计算，可能与印刷页码不同。':'Word 预览由转换生成，排版可能变化；不能据此保证原始排版一致。问题按段落或表格定位。';
  const download=$('#left-download');download.hidden=['extracted','chunks'].includes(left);download.href=`/api/documents/${doc.id}/file/${left}`;
  download.textContent=left==='converted'?'下载转换副本 ↗':'下载原文件 ↗';
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
  if(!await ask('删除这份文档？','将删除原文件、转换副本、提取结果及关联数据。之后的新检索不得使用该文档。相关检索结果将失效。','确认删除'))return;
  try{await api(`/api/documents/${id}`,{method:'DELETE'});if(current?.id===id)back();await refresh();toast('文档及处理副本已删除。');}catch(e){toast(e.message);await refresh();}
}
async function retryDoc(id){try{await api(`/api/documents/${id}/retry`,{method:'POST'});await refresh();toast('已加入处理队列。');}catch(e){toast(e.message);}}
async function reviewDoc(action,outcome='uncertain'){
  if(!current)return;
  const reviewer=$('#reviewer').value.trim(),note=$('#review-note').value.trim();
  if(!reviewer){$('#reviewer').focus();return toast('请先填写审核人姓名或工号。');}
  const checks=Object.fromEntries([...document.querySelectorAll('[data-review-check]')].map(el=>[el.dataset.reviewCheck,el.checked]));
  if(action==='accept'){
    if((current.admission?.requirements||[]).some(r=>checks[r.key]!==true))return toast('请先逐项核对并勾选确认。有错误或无法判断时，请选择暂不入库。');
    if(!await ask('确认当前内容可用？','确认后自动进行切分；本地服务启用时建立索引。已有风险和复核记录仍保留，只有索引有效才可检索。已知错误不能仅通过接受风险放行。','确认使用'))return;
  }
  try{await api(`/api/documents/${current.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,outcome,checks,reviewer,note,revision:current.revision})});await refresh();toast(action==='accept'?'已确认，自动进入待构建；风险提示仍保留。':'已暂缓入库，请修正或更换文件后重新检查。');}catch(e){toast(e.message);}
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
window.addEventListener('DOMContentLoaded',()=>{
 searchUI=window.P18Search.create({api,esc,onShow(){ragUI?.hide();current=null;detailRequest++;previewRequest++;$('#list-view').hidden=true;$('#detail-view').hidden=true;$('#search-view').hidden=false;$('#nav-documents').classList.remove('active');$('#nav-search').classList.add('active');$('#current-page').textContent='知识检索';}});
 searchUI.sync(records,semanticHealth);$('#nav-search').onclick=()=>{searchUI.show();refresh();};
 ragUI=window.P18Rag.create({api,esc,onShow(){searchUI?.hide();current=null;detailRequest++;previewRequest++;$('#list-view').hidden=true;$('#detail-view').hidden=true;$('#search-view').hidden=true;$('#rag-view').hidden=false;$('#nav-documents').classList.remove('active');$('#nav-search').classList.remove('active');$('#nav-rag').classList.add('active');$('#current-page').textContent='知识问答';}});$('#nav-rag').onclick=()=>ragUI.show();
});
document.addEventListener('click',e=>{const b=e.target.closest('[data-index-retry]');if(b)retryIndex(b.dataset.indexRetry);});
$('#upload-open').onclick=openUpload;$('#empty-upload').onclick=openUpload;$('#file-input').onchange=e=>chooseFiles(e.target.files);$('#upload-submit').onclick=submitUpload;
$('#dropzone').ondragover=e=>{e.preventDefault();$('#dropzone').classList.add('dragover');};$('#dropzone').ondragleave=()=>$('#dropzone').classList.remove('dragover');$('#dropzone').ondrop=e=>{e.preventDefault();$('#dropzone').classList.remove('dragover');chooseFiles(e.dataTransfer.files);};
$('#upload-dialog').addEventListener('cancel',e=>{if(uploadBusy)e.preventDefault();});
$('#detail-delete').onclick=()=>current&&removeDoc(current.id);$('#accept').onclick=()=>reviewDoc('accept');$('#hold').onclick=()=>reviewDoc('hold','uncertain');$('#incorrect').onclick=()=>reviewDoc('hold','incorrect');
document.addEventListener('click',e=>{if(e.target.closest('[data-generate-chunks]'))generateChunks();else{const source=e.target.closest('[data-chunk-page],[data-chunk-block]');if(source)locateChunkSource(source);}});
$('#preview-zoom').onchange=e=>{previewZoom=Number(e.target.value);renderPanes();};
$('#reparse').onclick=async()=>{
 if(!current||!await ask('重新解析？','将生成新解析版本，旧复核结论和切分结果不再沿用，历史审核记录保留。','重新解析'))return;
 try{await api(`/api/documents/${current.id}/reparse`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.revision})});await openDetail(current.id);}catch(e){toast(e.message);}
};
document.addEventListener('click',e=>{const b=e.target.closest('[data-preview-page]');if(b){page=Number(b.dataset.previewPage);$('#left-kind').value='original';renderPanes();}});
$('#left-kind').onchange=renderPanes;$('#right-kind').onchange=renderPanes;$('#page-prev').onclick=()=>{if(page>1){page--;renderPanes();}};$('#page-next').onclick=()=>{if(page<previewPages){page++;renderPanes();}};
document.addEventListener('click',e=>{const button=e.target.closest('[data-open],[data-delete],[data-retry],[data-issue]');if(!button)return;if(button.dataset.open)openDetail(button.dataset.open);else if(button.dataset.delete)removeDoc(button.dataset.delete);else if(button.dataset.retry)retryDoc(button.dataset.retry);else focusIssue(Number(button.dataset.issue));
});
refresh();
async function poll(){await refresh();const busy=records.some(d=>busyStates.has(d.state)||['waiting','building'].includes(d.index?.status));setTimeout(poll,document.hidden?20000:busy?4000:10000);}setTimeout(poll,4000);
}
