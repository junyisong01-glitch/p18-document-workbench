/* View states come from actual local/API events, never a simulated percentage. */
(function(root){
 const phases={retrieving:0,selecting:1,confirming:1,generating:2,answered:3};
 function steps(phase,error=false){const current=phases[phase]??-1;return ['本地检索','确认外发范围','生成回答'].map((label,index)=>({label,state:index<current?'complete':index===current?(error?'error':'active'):'pending'}));}
 function expired(preview,now=Date.now()){return !preview||!Number.isFinite(preview.expiresAt)||now>=preview.expiresAt;}
 function sourceView(ext,loaded,boxes){return ext==='.pdf'&&loaded&&Array.isArray(boxes)&&boxes.length>0?'original':'excerpt';}
 root.P18QaFlow={steps,expired,sourceView};
})(typeof window==='undefined'?module.exports:window);
