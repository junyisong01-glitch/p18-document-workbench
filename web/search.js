/* Semantic retrieval uses only the existing, same-origin P18 backend. */
(function () {
  const indexLabels = {not_started:'待建立索引',waiting:'等待构建',building:'正在构建',complete:'已建立、可检索',failed:'构建失败',stale:'索引已失效',blocked:'未满足入库条件',disabled:'本地检索未启用',unavailable:'本地检索不可用'};
  function indexLabel(index) {
    if (index?.status==='complete' && index.searchable!==true) return '索引已失效';
    return indexLabels[index?.status] || '待建立索引';
  }
  function sourcePage(result, doc, source) {
    if (doc.ext==='.pdf') return Number.isInteger(source?.page) && source.page>0 ? source.page : null;
    const value=source?.preview_pages?.original ?? doc.result?.blocks?.find(b=>b.id===source?.block_id)?.preview_pages?.original;
    return Number.isInteger(value) && value>0 ? value : null;
  }
  function hitIsCurrent(hit, records) {
    const doc=records.find(d=>d.id===hit.document_id);
    return !!doc && doc.revision===hit.revision && doc.index?.searchable===true && doc.index?.status==='complete' && !!hit.index_token && doc.index.token===hit.index_token;
  }
  function create({api,esc,onShow}) {
    const $=s=>document.querySelector(s);
    let records=[], health=null, visible=false, busy=false, hits=[], selected=null, selectedDoc=null;
    let searchEpoch=0, previewEpoch=0, queryAbort=null, previewAbort=null, previewPage=0, pageCount=0, currentSource=null;
    function resetPreview(message='搜索后选择相关片段，在这里核对来源。') {
      previewEpoch++;previewAbort?.abort();selectedDoc=null;previewPage=0;pageCount=0;
      $('#semantic-preview-name').textContent='尚未选择片段';$('#semantic-download').hidden=true;
      $('#semantic-source-note').textContent=message;$('#semantic-page-label').textContent='暂无预览';
      $('#semantic-prev').disabled=true;$('#semantic-next').disabled=true;
      $('#semantic-preview-content').innerHTML='<p class="pane-empty">原文预览将在此显示。</p>';
    }
    function setBusy(value) {busy=value;$('#semantic-submit').disabled=value||!health?.enabled||health?.setup?.ready===false;$('#semantic-submit').textContent=value?'检索中…':'搜索';$('#semantic-results').setAttribute('aria-busy',String(value));}
    function renderService() {
      if (!health?.enabled) {
        const error=health?.error;
        $('#semantic-service').textContent=(typeof error==='string'?error:error?.message) || (health?.setup?.ready?'本地模型已缓存，但语义检索尚未启用。请通过原工作台启动入口开启，已运行的旧服务需要先安全重启。':health?.setup?.message) || '本地语义检索未启用或当前服务版本较旧，请按启动说明检查；文档管理仍可使用。';
      } else if(health.setup?.ready===false){
        $('#semantic-service').textContent=health.setup.message+' 文档管理可继续使用。';
      } else {
        const ready=records.filter(d=>d.index?.searchable).length;
        const building=records.filter(d=>['waiting','building'].includes(d.index?.status)).length;
        const failures=records.filter(d=>d.index?.status==='failed').length;
        $('#semantic-service').textContent=`本地 Qwen 语义检索 · ${ready} 份可检索${building?` · ${building} 份正在准备索引`:''}${failures?` · ${failures} 份构建失败，可在文档管理重试`:''}。${health.model_loaded?'模型已加载。':'模型已缓存，等待首次构建或检索时加载。'}`;
      }
      setBusy(busy);
    }
    function sync(nextRecords,nextHealth) {
      records=nextRecords;health=nextHealth;
      const value=$('#semantic-scope').value;
      const options='<option value="">全部文档</option>'+records.map(d=>`<option value="${esc(d.id)}">${esc(d.name)} · ${esc(indexLabel(d.index))}</option>`).join('');
      if($('#semantic-scope').innerHTML!==options){$('#semantic-scope').innerHTML=options;$('#semantic-scope').value=records.some(d=>d.id===value)?value:'';}
      const previous=hits.length;
      hits=hits.filter(hit=>hitIsCurrent(hit,records));
      if(hits.length!==previous){
        if(!hits.some(h=>h.chunk_id===selected)){selected=null;resetPreview('选中内容的版本或审核状态已变化，请重新搜索。');}
        $('#semantic-status').textContent='部分结果已因文档或索引状态变化移除，请重新搜索。';renderHits();
      }
      if(!health?.enabled&&hits.length){hits=[];selected=null;resetPreview('检索服务当前不可用，请检查服务状态。');renderHits();}
      renderService();
    }
    function renderHits() {
      $('#semantic-count').textContent=hits.length?`${hits.length} 条真实结果`:'暂无结果';
      $('#semantic-results').innerHTML=hits.map((hit,i)=>{
        const long=Array.from(hit.text).length>240;
        const snippet=Array.from(hit.text).slice(0,240).join('');
        return `<article class="semantic-card${selected===hit.chunk_id?' selected':''}" data-result-card="${i}"><button type="button" class="result-select" data-select-hit="${i}" aria-pressed="${selected===hit.chunk_id}"><span class="result-rank">${hit.rank}</span><span><strong>${esc(hit.document_name)}</strong>${hit.section?`<small>${esc(hit.section)}</small>`:''}</span><span class="result-score">相似度 ${Number(hit.score).toFixed(4)}</span></button>${long?`<details class="result-text"><summary><span class="result-excerpt">${esc(snippet)}…</span><span class="expand-result">展开完整片段</span></summary><pre>${esc(hit.text)}</pre></details>`:`<pre class="result-text">${esc(hit.text)}</pre>`}${hit.risk?.incomplete?'<p class="preview-warning">来源文档存在内容不完整风险，使用时请核对原文。</p>':''}${hit.risk?.quality==='review'?'<p class="source-note">来源已复核，原检查提示仍保留。</p>':''}<div class="result-sources">${(hit.sources||[]).map((src,j)=>`<button type="button" class="text-button" data-hit-source="${i}" data-source-index="${j}">${esc(src.label||'文档级来源')} · 查看原文 ↗</button>`).join('')||`<button type="button" class="text-button" data-select-hit="${i}">查看原文 ↗</button>`}</div></article>`;
      }).join('');
    }
    async function selectHit(index,sourceIndex=0) {
      const hit=hits[index];if(!hit)return;
      const epoch=++previewEpoch;previewAbort?.abort();previewAbort=new AbortController();
      selected=hit.chunk_id;renderHits();$('#semantic-preview-name').textContent=hit.document_name;
      $('#semantic-download').hidden=true;$('#semantic-preview-content').innerHTML='<p class="pane-empty">正在核对来源并加载原文…</p>';
      previewPage=0;pageCount=0;$('#semantic-prev').disabled=true;$('#semantic-next').disabled=true;
      try {
        const [doc,status]=await Promise.all([api(`/api/documents/${hit.document_id}`,{signal:previewAbort.signal}),api(`/api/documents/${hit.document_id}/index`,{signal:previewAbort.signal})]);
        if(epoch!==previewEpoch||!visible)return;
        if(doc.revision!==hit.revision || !status.searchable || status.token!==hit.index_token)throw new Error('该片段已经失效，请重新检索。');
        selectedDoc=doc;currentSource=hit.sources?.[sourceIndex]||{};
        $('#semantic-download').href=`/api/documents/${doc.id}/file/original`;$('#semantic-download').hidden=false;
        const meta=await api(`/api/documents/${doc.id}/preview/original/meta`,{signal:previewAbort.signal});
        if(epoch!==previewEpoch||!visible)return;
        pageCount=meta.pages;const target=sourcePage(hit,doc,currentSource);
        if(target && target<=pageCount){previewPage=target;renderPreview();}
        else {
          $('#semantic-source-note').textContent=`${currentSource.label||'文档级来源'}。当前无法可靠确定对应预览页，不自动猜测页码。${doc.ext!=='.pdf'?'Word 使用系统转换预览，分页可能与原文件不同。':''}`;
          $('#semantic-page-label').textContent='未定位到具体页';
          $('#semantic-preview-content').innerHTML='<p class="pane-empty">可以下载原文件按上述结构位置核对，或从首页浏览文档；首页不是片段定位结果。</p><button type="button" class="secondary" id="semantic-browse">从首页浏览文档（非来源定位）</button>';
        }
      } catch(error) {if(epoch===previewEpoch && error.name!=='AbortError'){$('#semantic-source-note').textContent='无法显示当前原文，请核对文档和索引状态。';$('#semantic-preview-content').innerHTML=`<p class="pane-empty">${esc(error.message)}</p>`;}}
    }
    function renderPreview() {
      if(!selectedDoc||!previewPage)return;
      const doc=selectedDoc;
      const target=sourcePage({},doc,currentSource);
      $('#semantic-source-note').textContent=`${currentSource?.label||'文档级来源'}。${target===previewPage?(doc.ext==='.pdf'?'定位至原 PDF 物理页。':'定位至系统转换预览页，可能与 Word 分页不同。'):'当前为文档浏览页，不表示片段精确定位。'}${doc.ext!=='.pdf'?' 转换预览可能不完整，请结合原文件核对。':''}`;
      $('#semantic-page-label').textContent=`第 ${previewPage} / ${pageCount} 页${doc.ext!=='.pdf'?' · 转换预览':''}`;
      $('#semantic-prev').disabled=previewPage<=1;$('#semantic-next').disabled=previewPage>=pageCount;
      $('#semantic-preview-content').innerHTML=`<img src="/api/documents/${doc.id}/preview/original/${previewPage}?revision=${doc.revision}" alt="${esc(doc.name)} · ${doc.ext==='.pdf'?'物理页':'系统转换预览页'} ${previewPage}">`;
      $('#semantic-preview-content img').onerror=()=>{$('#semantic-preview-content').innerHTML='<p class="pane-empty">原文图像加载失败，请重选片段或下载原文件核对。</p>';};
    }
    async function submit(event) {
      event.preventDefault();const query=$('#semantic-query').value.trim();if(!query||busy)return;
      const epoch=++searchEpoch;queryAbort?.abort();queryAbort=new AbortController();
      hits=[];selected=null;renderHits();resetPreview();setBusy(true);$('#semantic-status').textContent='正在本机生成查询向量并检索…';
      try {
        const documentId=$('#semantic-scope').value;
        const result=await api('/api/search',{method:'POST',signal:queryAbort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({query,...(documentId?{document_id:documentId}:{})})});
        if(epoch!==searchEpoch||!visible)return;
        // Refresh metadata before accepting results into the UI cache.
        records=await api('/api/documents',{signal:queryAbort.signal});
        if(epoch!==searchEpoch||!visible)return;
        hits=(result.results||[]).filter(h=>hitIsCurrent(h,records));renderHits();
        $('#semantic-status').textContent=hits.length?`问题：“${query}” · 点击片段查看右侧原文。`:result.message||'没有当前有效结果，请检查范围或等待索引完成。';
        if(hits.length)await selectHit(0);
      } catch(error) {if(epoch===searchEpoch&&error.name!=='AbortError'){$('#semantic-status').textContent=`检索未完成：${error.message}`;hits=[];renderHits();resetPreview('没有可供预览的有效结果。');}}
      finally {if(epoch===searchEpoch)setBusy(false);}
    }
    $('#semantic-form').addEventListener('submit',submit);
    $('#semantic-scope').onchange=()=>{searchEpoch++;queryAbort?.abort();setBusy(false);hits=[];selected=null;renderHits();resetPreview();$('#semantic-status').textContent='搜索范围已切换，请重新搜索。';};
    $('#semantic-results').onclick=event=>{const source=event.target.closest('[data-hit-source]'),button=event.target.closest('[data-select-hit]');if(source)selectHit(Number(source.dataset.hitSource),Number(source.dataset.sourceIndex));else if(button)selectHit(Number(button.dataset.selectHit));};
    $('#semantic-prev').onclick=()=>{if(previewPage>1){previewPage--;renderPreview();}};
    $('#semantic-next').onclick=()=>{if(previewPage<pageCount){previewPage++;renderPreview();}};
    $('#semantic-preview-content').onclick=event=>{if(event.target.closest('#semantic-browse')){previewPage=1;renderPreview();}};
    return {sync,offline(message){health={enabled:false,error:message};searchEpoch++;queryAbort?.abort();hits=[];selected=null;setBusy(false);renderHits();resetPreview('服务连接中断，当前无法核验来源版本。恢复后请重新搜索。');$('#semantic-status').textContent='检索服务连接中断，请检查本机服务后重试。';renderService();},show(){visible=true;onShow();renderService();if(selected){const i=hits.findIndex(h=>h.chunk_id===selected);if(i>=0)selectHit(i);}},hide(){visible=false;searchEpoch++;previewEpoch++;queryAbort?.abort();previewAbort?.abort();setBusy(false);},get visible(){return visible;}};
  }
  window.P18Search={create,indexLabel,sourcePage,hitIsCurrent};
})();
