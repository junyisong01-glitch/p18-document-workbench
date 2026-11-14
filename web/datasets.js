/* Data-source choice never supplies identity or grants read/egress permission. */
(async function(){
  const response=await fetch('/api/library/datasets',{cache:'no-store'});
  if(!response.ok)return;
  const data=await response.json();
  const panel=document.createElement('section');panel.className='p18-datasets';panel.setAttribute('aria-label','知识库切换');
  const label=document.createElement('label');label.textContent='当前知识库';
  const select=document.createElement('select');select.setAttribute('aria-label','选择知识库');
  for(const item of data.datasets){const option=document.createElement('option');option.value=item.id;option.textContent=item.name;select.append(option);}
  select.value=data.selected;label.append(select);
  const note=document.createElement('small');note.textContent=data.selected==='qichen30'?'按登录岗位过滤 · 仅本地查看 · 禁止外发':'现有演示库 · 权限和许可规则保持';
  const error=document.createElement('span');error.setAttribute('role','status');
  panel.append(label,note,error);document.body.append(panel);
  select.onchange=async()=>{
    select.disabled=true;
    try{
      const reply=await fetch('/api/library/datasets',{method:'POST',headers:{'Content-Type':'application/json','X-P18-Client':'workbench'},body:JSON.stringify({dataset:select.value})});
      if(!reply.ok)throw new Error('切换失败，请重新登录后重试');
      sessionStorage.clear();location.assign('/library/');
    }catch(e){error.textContent=e.message;select.disabled=false;}
  };
})().catch(()=>{});
