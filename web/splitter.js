/* Shared pointer/keyboard divider. Changes layout only; no business state. */
(function(root){
 function limits(request,total,min=280,max=760,reserve=320){const low=Math.min(min,total*.45),high=Math.max(low,Math.min(max,total-reserve,total*.7));return Math.max(low,Math.min(request,high));}
 function bind({handle,container,value,apply,side='right',min=280,max=760,reserve=320}){
  let current=value;
  function resize(next){const total=container.getBoundingClientRect().width;if(total<=0)return;current=limits(next,total,min,max,reserve);apply(current);handle.setAttribute('aria-valuemin',Math.round(Math.min(min,total*.45)));handle.setAttribute('aria-valuemax',Math.round(limits(Infinity,total,min,max,reserve)));handle.setAttribute('aria-valuenow',Math.round(current));}
  handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.tabIndex=0;
  function stop(e){handle.onpointermove=null;container.classList.remove('is-resizing');if(e&&handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);}
  handle.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();handle.setPointerCapture(e.pointerId);container.classList.add('is-resizing');handle.onpointermove=p=>{const r=container.getBoundingClientRect();resize(side==='right'?r.right-p.clientX:p.clientX-r.left);};};
  handle.onpointerup=stop;handle.onlostpointercapture=()=>stop();handle.onpointercancel=stop;
  handle.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();resize(e.key==='Home'?0:e.key==='End'?Infinity:current+((e.key==='ArrowLeft')===(side==='right')?20:-20));};
  const observer=new ResizeObserver(()=>{if(!handle.hidden)resize(current);});observer.observe(container);resize(current);return {resize:()=>resize(current),dispose(){observer.disconnect();stop();}};
 }
 root.P18Splitter={limits,bind};
})(typeof window==='undefined'?module.exports:window);
