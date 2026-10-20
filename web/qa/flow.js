/* View states come from actual local/API events, never a simulated percentage. */
(function(root){
 const phases={retrieving:0,selecting:1,confirming:2,generating:3,answered:4};
 function steps(phase,error=false){const current=phases[phase]??-1;return ['本地检索','选择证据','人工确认外发','生成回答'].map((label,index)=>({label,state:index<current?'complete':index===current?(error?'error':'active'):'pending'}));}
 function expired(preview,now=Date.now()){return !preview||!Number.isFinite(preview.expiresAt)||now>=preview.expiresAt;}
 function sourceView(ext,loaded,boxes){return ext==='.pdf'&&loaded&&Array.isArray(boxes)&&boxes.length>0?'original':'excerpt';}
 function recovery(code){
  const resetSession=['session_expired','session_changed','turn_expired','history_invalid','draft_expired','request_failed'].includes(code);
  const refresh=resetSession||['ticket_expired','selection_changed','evidence_stale','config_changed'].includes(code);
  return {refresh,resetSession};
 }
 function receivingTarget(p){
  try{
   const base=p.destination,endpoint=p.request_endpoint;
   if(typeof base!=='string'||typeof endpoint!=='string'||!base||/[\s\x00-\x1f?#\\]/.test(base))return false;
   const u=new URL(base);
   return u.protocol==='https:'&&!!u.hostname&&!u.username&&!u.password&&!u.search&&!u.hash&&endpoint===base.replace(/\/+$/,'')+'/chat/completions';
  }catch(_){return false;}
 }
 root.P18QaFlow={steps,expired,sourceView,recovery,receivingTarget};
})(typeof window==='undefined'?module.exports:window);
