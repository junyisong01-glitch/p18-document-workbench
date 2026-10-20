/* Local human approval only. The backend owns identity, status and permission. */
(() => {
  const $=s=>document.querySelector(s);
  let doc, refresh, snapshot, opener, busy=false;
  const checks=['no_sensitive_content','third_party_terms_checked','no_restricted_content'];
  const dialog=()=>$('#external-review-dialog');
  function ready(){return !busy && !!dialog().querySelector('input[name="external-classification"]:checked') && checks.every(k=>$('#external-'+k).checked);}
  function update(){ $('#external-confirm').disabled=!ready(); }
  function close(){if(busy)return;dialog().close();opener?.focus();}
  async function send(revoke=false){
    if(busy || (!revoke&&!ready()))return;
    const identity=revoke?{id:doc.id,...doc.external_permission}:snapshot;
    const body={revision:identity.revision,fingerprint:identity.fingerprint};
    if(!revoke){body.classification=dialog().querySelector('input[name="external-classification"]:checked').value;body.checks=Object.fromEntries(checks.map(k=>[k,$('#external-'+k).checked]));}
    busy=true;update();$('#external-revoke').disabled=true;
    try{
      const r=await fetch(`/api/documents/${identity.id}/external-permission${revoke?'/revoke':''}`,{method:'POST',headers:{'Content-Type':'application/json','X-P18-Client':'workbench'},body:JSON.stringify(body)});
      const result=await r.json();if(!r.ok)throw Error(result.detail?.message||'权限操作失败，请刷新详情后重试。');
      dialog().close();await refresh();
      if(!revoke)$('#external-success-dialog').showModal();
      else $('#external-inline-status').textContent='外发许可已撤销；请在知识问答中重新检索。';
    }catch(e){$('#external-error').textContent=e.message;$('#external-inline-status').textContent=e.message;}
    finally{busy=false;update();$('#external-review').disabled=!doc.external_permission?.can_review;$('#external-revoke').disabled=!doc.external_permission?.allowed;}
  }
  window.P18ExternalPermission={render(value,reload){
    doc=value;refresh=reload;const p=doc.external_permission||{};
    $('#external-badge').textContent=p.allowed?'已审核 · 可外发':'仅本地 · 未获外发许可';
    $('#external-badge').className='external-badge '+(p.allowed?'allowed':'');
    $('#external-description').textContent=p.allowed?'仅当前文档版本获准；用于问答仍需重新检索、选择证据并逐轮确认外发内容。':'本地检索与外发许可相互独立。未获许可的证据可本地预览，不能发送给外部模型。';
    $('#external-review').disabled=busy||!p.can_review;
    $('#external-revoke').disabled=busy||!p.allowed;
    $('#external-inline-status').textContent=p.can_review?'':'请先完成解析及必要的内容复核；外发审核不能代替入库复核。';
  }};
  document.addEventListener('DOMContentLoaded',()=>{
    $('#external-review').onclick=()=>{
      opener=$('#external-review');snapshot={id:doc.id,...doc.external_permission};
      $('#external-document').textContent=`文档：${doc.name}（解析版本 v${doc.revision}）`;
      dialog().querySelectorAll('input').forEach(x=>x.checked=false);$('#external-error').textContent='';update();dialog().showModal();
    };
    dialog().addEventListener('change',update);dialog().addEventListener('cancel',e=>{if(busy)e.preventDefault();});
    $('#external-cancel').onclick=close;$('#external-close').onclick=close;
    $('#external-confirm').onclick=()=>send(false);$('#external-revoke').onclick=()=>send(true);
    $('#external-success-ok').onclick=()=>{$('#external-success-dialog').close();opener?.focus();};
  });
})();
