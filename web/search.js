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
    if(hit.members && !hit.members.every(member=>hitIsCurrent(member,records)))return false;
    const doc=records.find(d=>d.id===hit.document_id);
    return !!doc && doc.revision===hit.revision && doc.index?.searchable===true && doc.index?.status==='complete' && !!hit.index_token && doc.index.token===hit.index_token;
  }
  function create({api,esc,onShow}) {
    const $=s=>document.querySelector(s);
    let records=[],health=null,visible=false,busy=false,hits=[],selected=null,selectedDoc=null,currentHit=null,currentSource=null;
    let searchEpoch=0,previewEpoch=0,queryAbort=null,previewAbort=null,previewPage=0,pageCount=0,scale=1,blob=null,highlighting={pages:[]};
    const metadata=new Map();
    const layout=$('.retrieval-layout');window.P18Splitter.bind({handle:$('#search-divider'),container:layout,value:360,side:'left',min:260,max:680,reserve:360,apply:w=>layout.style.setProperty('--results-width',w+'px')});
    const key=h=>[h.document_id,h.revision,h.index_token,h.chunk_id].join(':');
    const params=h=>new URLSearchParams({revision:h.revision,index_token:h.index_token,chunk_id:h.chunk_id});
    function release(){if(blob)URL.revokeObjectURL(blob);blob=null;}
    function resetPreview(message='搜索后选择相关片段，在这里核对来源。') {
      previewEpoch++;previewAbort?.abort();release();selectedDoc=currentHit=null;previewPage=pageCount=0;scale=1;highlighting={pages:[]};
      $('#semantic-preview-name').textContent='尚未选择片段';$('#semantic-download').hidden=true;
      $('#semantic-source-note').textContent=message;$('#semantic-page-label').textContent='暂无预览';
      $('#semantic-prev').disabled=$('#semantic-next').disabled=$('#semantic-zoom-in').disabled=$('#semantic-zoom-out').disabled=true;
      $('#semantic-zoom-label').textContent='适宽';$('#semantic-preview-content').innerHTML='<p class="pane-empty">原文预览将在此显示。</p>';
    }
    function setBusy(value){busy=value;$('#semantic-submit').disabled=value||!health?.enabled||health?.setup?.ready===false;$('#semantic-submit').textContent=value?'检索中…':'搜索';$('#semantic-results').setAttribute('aria-busy',String(value));}
    function renderService(){
      if(!health?.enabled){const error=health?.error;$('#semantic-service').textContent=(typeof error==='string'?error:error?.message)||health?.setup?.message||'本地语义检索未启用，文档管理仍可使用。';}
      else if(health.setup?.ready===false)$('#semantic-service').textContent=health.setup.message+' 文档管理可继续使用。';
      else {const ready=records.filter(d=>d.index?.searchable).length,building=records.filter(d=>['waiting','building'].includes(d.index?.status)).length,failed=records.filter(d=>d.index?.status==='failed').length;$('#semantic-service').textContent=`本地 Qwen 语义检索 · ${ready} 份可检索${building?` · ${building} 份索引准备中`:''}${failed?` · ${failed} 份索引失败`:''}`;}
      setBusy(busy);
    }
    function sync(nextRecords,nextHealth){
      records=nextRecords;health=nextHealth;const value=$('#semantic-scope').value;
      const options='<option value="">全部文档</option>'+records.map(d=>`<option value="${esc(d.id)}">${esc(d.name)} · ${esc(indexLabel(d.index))}</option>`).join('');
      if($('#semantic-scope').innerHTML!==options){$('#semantic-scope').innerHTML=options;$('#semantic-scope').value=records.some(d=>d.id===value)?value:'';}
      const count=hits.length;hits=hits.filter(hit=>hitIsCurrent(hit,records));
      if(count!==hits.length){if(!hits.some(h=>h.chunk_id===selected)){selected=null;resetPreview('来源版本或审核状态已变化，请重新搜索。');}$('#semantic-status').textContent='已移除失效结果，请重新搜索。';renderHits();}
      if(!health?.enabled&&hits.length){hits=[];selected=null;resetPreview('本地检索服务当前不可用。');renderHits();}renderService();
    }
    function location(hit){
      const doc=records.find(d=>d.id===hit.document_id)||{},meta=metadata.get(key(hit));
      if(window.P18SourceLocation)return window.P18SourceLocation.format(doc,{...hit,sources:hit.sources||[]},meta).text;
      return hit.section||'文档级来源';
    }
    function renderHits(){
      $('#semantic-count').textContent=hits.length?`${hits.length} 条真实结果`:'暂无结果';
      $('#semantic-results').innerHTML=hits.map((hit,i)=>{
        const snippet=Array.from(hit.text.replace(/\s+/g,' ').trim()).slice(0,90).join(''),long=Array.from(hit.text).length>90,members=hit.members||[hit];
        const sources=members.map((m,n)=>`<button type="button" class="text-button" data-hit-source="${i}" data-member-index="${n}">${members.length>1?esc(m.document_name)+' · ':''}查看原文 ↗</button>`).join('');
        const score=typeof hit.score==='number'&&Number.isFinite(hit.score)?hit.score.toFixed(4):'未提供';
        return `<article class="semantic-card${selected===hit.chunk_id?' selected':''}"><button type="button" class="result-select" data-select-hit="${i}" aria-pressed="${selected===hit.chunk_id}"><span class="result-rank">${esc(hit.rank)}</span><span class="result-title"><strong>${esc(hit.document_name)}</strong><small>${esc(location(hit))}</small></span><span class="result-score" title="向量相似度，不代表正确率">${score}</span></button>${long?`<details class="result-text"><summary>${esc(snippet)}…<span class="expand-result">展开</span></summary><pre>${esc(hit.text)}</pre></details>`:`<pre class="result-text">${esc(hit.text)}</pre>`}${members.some(m=>m.risk?.incomplete)?'<p class="preview-warning">来源存在内容不完整风险，请核对原文。</p>':''}${typeof hit.fusion_score==='number'?`<p class="retrieval-mode-note">混合排序 · RRF ${hit.fusion_score.toFixed(5)}；右上数值为向量相似度</p>`:'<p class="retrieval-mode-note">向量相似度，不代表答案正确率</p>'}<div class="result-sources">${sources}</div></article>`;
      }).join('');
    }
    function excerpt(message){$('#semantic-preview-content').innerHTML='<p class="preview-limit">'+esc(message)+'</p><pre class="search-excerpt">'+esc(currentHit?.text||'')+'</pre><button type="button" class="secondary" id="semantic-browse">从首页浏览文档（非片段定位）</button>';}
    async function selectHit(index,sourceIndex=0,memberIndex=0){
      const group=hits[index];if(!group)return;const hit=group.members?.[memberIndex]||group;
      resetPreview('正在核验来源身份及版本…');const epoch=previewEpoch;previewAbort=new AbortController();
      selected=group.chunk_id;renderHits();$('#semantic-preview-name').textContent=hit.document_name;
      try{
        const base='/api/documents/'+encodeURIComponent(hit.document_id),identity=params(hit);
        const checked=await api(base+'/source?'+identity,{signal:previewAbort.signal});if(epoch!==previewEpoch||!visible)return;
        selectedDoc=checked.document;currentHit={...hit,...checked.source};currentSource=currentHit.sources?.[sourceIndex]||{};
        $('#semantic-download').href=base+'/file/original?'+identity;$('#semantic-download').hidden=false;
        let meta;try{meta=await api(base+'/preview/original/meta?'+identity,{signal:previewAbort.signal});}catch(error){if(error.status===409)throw error;if(epoch===previewEpoch)excerpt('预览不可用，保留真实提取片段，可下载原件核对。');return;}
        if(epoch!==previewEpoch||!visible)return;pageCount=meta.pages;metadata.set(key(hit),meta);renderHits();
        try{highlighting=await api(base+'/source/highlight?'+identity,{signal:previewAbort.signal});}catch(error){if(error.status===409)throw error;highlighting={pages:[]};}
        if(epoch!==previewEpoch||!visible)return;
        const target=sourcePage(hit,selectedDoc,currentSource);
        if(target&&target<=pageCount){previewPage=target;await renderPreview();}
        else {$('#semantic-page-label').textContent='未确定具体页';$('#semantic-source-note').textContent=location(hit);excerpt('暂无法可靠定位原文页；以下为真实提取片段，不猜测Word页码。');}
      }catch(error){if(epoch===previewEpoch&&error.name!=='AbortError'){$('#semantic-download').hidden=true;$('#semantic-source-note').textContent='来源无法通过当前版本核验。';$('#semantic-preview-content').innerHTML='<p class="pane-empty">'+esc(error.message)+'</p>';}}
    }
    async function renderPreview(){
      if(!selectedDoc||!previewPage||!currentHit)return;
      const epoch=++previewEpoch,doc=selectedDoc,hit=currentHit,page=previewPage;
      previewAbort?.abort();previewAbort=new AbortController();const signal=previewAbort.signal;
      const target=sourcePage({},doc,currentSource),boxes=highlighting.pages?.find(p=>p.page===page)?.rects||[];
      $('#semantic-source-note').textContent=window.P18SourceLocation.format(doc,hit,{pages:pageCount}).text+(target!==page?' · 当前为手动浏览页':doc.ext!=='.pdf'?' · 转换预览分页可能不同于Word':'' )+(boxes.length?' · 原文已高亮':' · 无可靠精确高亮');
      $('#semantic-page-label').textContent=`第 ${page}/${pageCount} 页`;
      $('#semantic-prev').disabled=page<=1;$('#semantic-next').disabled=page>=pageCount;
      $('#semantic-zoom-in').disabled=scale>=2;$('#semantic-zoom-out').disabled=scale<=.75;$('#semantic-zoom-label').textContent=scale===1?'适宽':Math.round(scale*100)+'%';
      $('#semantic-preview-content').textContent='正在核验并读取真实原文…';
      try{
        const response=await fetch(`/api/documents/${encodeURIComponent(doc.id)}/preview/original/${page}?${params(hit)}&zoom=${Math.max(1,scale)}`,{signal});
        if(!response.ok){const error=new Error('来源已失效或原文预览不可用，请重新搜索。');error.status=response.status;throw error;}
        const data=await response.blob();if(epoch!==previewEpoch||!visible)return;release();blob=URL.createObjectURL(data);
        const painted=window.P18SourcePreview.paint($('#semantic-preview-content'),blob,boxes,doc.name+' · '+(doc.ext==='.pdf'?'PDF物理页':'系统转换预览页')+' '+page,'search-paper');
        painted.wrapper.style.width=(scale*100)+'%';painted.image.onerror=()=>{if(epoch===previewEpoch)excerpt('原文图像未能显示；以下保留真实提取片段。');};
      }catch(error){if(epoch===previewEpoch&&error.name!=='AbortError'){if(error.status===409){$('#semantic-download').hidden=true;$('#semantic-preview-content').textContent=error.message;}else excerpt('原文图像暂不可用；以下为已核验的真实提取片段。');}}
    }
    async function submit(event){
      event.preventDefault();const query=$('#semantic-query').value.trim();if(!query||busy)return;
      const epoch=++searchEpoch;queryAbort?.abort();queryAbort=new AbortController();hits=[];selected=null;renderHits();resetPreview();setBusy(true);$('#semantic-status').textContent='正在本机生成查询向量并检索…';
      try{
        const documentId=$('#semantic-scope').value;
        const result=await api('/api/search',{method:'POST',signal:queryAbort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({query,...(documentId?{document_id:documentId}:{})})});
        if(epoch!==searchEpoch||!visible)return;records=await api('/api/documents',{signal:queryAbort.signal});if(epoch!==searchEpoch||!visible)return;
        hits=(result.results||[]).filter(h=>hitIsCurrent(h,records));renderHits();$('#semantic-status').textContent=hits.length?'相关片段仅供参考，请核对原文。':result.message||'没有当前有效结果。';
        await Promise.all(hits.map(async hit=>{for(const member of hit.members||[hit]){try{const meta=await api(`/api/documents/${encodeURIComponent(member.document_id)}/preview/original/meta?${params(member)}`,{signal:queryAbort.signal});if(epoch===searchEpoch)metadata.set(key(member),meta);}catch(error){/* Unknown page stays unknown; selection rechecks identity. */}}}));
        if(epoch!==searchEpoch||!visible)return;renderHits();if(hits.length)await selectHit(0);
      }catch(error){if(epoch===searchEpoch&&error.name!=='AbortError'){$('#semantic-status').textContent='检索未完成：'+error.message;hits=[];renderHits();resetPreview('没有可供预览的有效结果。');}}
      finally{if(epoch===searchEpoch)setBusy(false);}
    }
    $('#semantic-form').addEventListener('submit',submit);
    $('#semantic-scope').onchange=()=>{searchEpoch++;queryAbort?.abort();setBusy(false);hits=[];selected=null;renderHits();resetPreview();$('#semantic-status').textContent='搜索范围已切换，请重新搜索。';};
    $('#semantic-results').onclick=event=>{const source=event.target.closest('[data-hit-source]'),button=event.target.closest('[data-select-hit]');if(source)selectHit(Number(source.dataset.hitSource),0,Number(source.dataset.memberIndex||0));else if(button)selectHit(Number(button.dataset.selectHit));};
    $('#semantic-prev').onclick=()=>{if(previewPage>1){previewPage--;renderPreview();}};$('#semantic-next').onclick=()=>{if(previewPage<pageCount){previewPage++;renderPreview();}};
    $('#semantic-zoom-in').onclick=()=>{scale=Math.min(2,scale+.25);renderPreview();};$('#semantic-zoom-out').onclick=()=>{scale=Math.max(.75,scale-.25);renderPreview();};
    $('#semantic-preview-content').onclick=event=>{if(event.target.closest('#semantic-browse')){previewPage=1;renderPreview();}};
    return {sync,offline(message){health={enabled:false,error:message};searchEpoch++;queryAbort?.abort();hits=[];selected=null;setBusy(false);renderHits();resetPreview();$('#semantic-status').textContent='检索服务连接中断，请检查本机服务后重试。';renderService();},show(){visible=true;onShow();renderService();if(selected){const i=hits.findIndex(h=>h.chunk_id===selected);if(i>=0)selectHit(i);}},hide(){visible=false;searchEpoch++;previewEpoch++;queryAbort?.abort();previewAbort?.abort();release();setBusy(false);},get visible(){return visible;}};
  }
  window.P18Search={create,indexLabel,sourcePage,hitIsCurrent};
})();
