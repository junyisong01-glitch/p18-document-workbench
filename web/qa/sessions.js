/* Tab-memory sessions only. No permissions or server evidence manufactured here. */
(function(root){
 function create(){let count=0,active=null;const items=[];return {
  new(){const item={id:'local-'+(++count),title:'新对话',state:null};items.unshift(item);active=item.id;return item;},
  save(state){const item=items.find(s=>s.id===active);if(item){item.state=state;item.title=state.turns?.[0]?.question||state.question||'新对话';}},
  select(id){const item=items.find(s=>s.id===id);if(!item)throw Error('会话不存在');active=id;return item;},
  list(){return items.map(s=>({id:s.id,title:s.title,active:s.id===active}));},
  get current(){return active;}
 };}
 root.P18QaSessions={create};
})(typeof window==='undefined'?module.exports:window);
