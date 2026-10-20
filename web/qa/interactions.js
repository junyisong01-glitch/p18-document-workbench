/* Session-only UI state. No evidence or permission decisions live here. */
(function(root){
 const api={
  width(request,available){return Math.max(Math.min(280,available*.5),Math.min(request,Math.min(760,available*.6,available-320)));},
  add(turns,response,question,index){
   if(index!==null){const t=turns[index];if(!t||t.question!==question||(!t.detached&&t.turn_id!==response.turn_id))throw Error('原问题身份已变化');if(t.detached){if(!response.session_id||!response.turn_id)throw Error('恢复后的问题身份缺失');t.turn_id=response.turn_id;t.detached=false;}t.versions.push(response);t.active=t.versions.length-1;return;}
   turns.push({question,turn_id:response.turn_id,versions:[response],active:0});
  }
 };
 if(typeof module!=='undefined')module.exports=api;else root.P18QaInteractions=api;
})(typeof window==='undefined'?globalThis:window);
