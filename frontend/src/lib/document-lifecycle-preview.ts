// Presentation-only fixtures for the isolated preview. Never persisted as audit events.
export type LifecycleEvent = {actor?:string;at?:string|number;automatic?:boolean}
export type Lifecycle = {submitted?:LifecycleEvent|null;reviewed?:LifecycleEvent|null;published?:LifecycleEvent|null}
const people:Record<string,[string[],string]>={
  '研发部':[['qichen_rd','qichen_ops','qichen_qa'],'qichen_rd_head'],
  '生产制造部':[['qichen_prd'],'qichen_prd_head'],
  '财务部':[['qichen_fin'],'qichen_fin_head'],
  '人力资源部':[['qichen_hr'],'qichen_hr_head'],
  '行政安全部':[['qichen_adm'],'qichen_adm_head'],
}
export function previewDocumentLifecycle(key:string,department:string,legacy:boolean,actual:Lifecycle|undefined,isolated:boolean):{facts:Lifecycle|undefined;simulated:boolean}{
  if(!isolated||!legacy||actual?.submitted||actual?.reviewed||actual?.published)return {facts:actual,simulated:false}
  let seed=0
  for(const ch of key)seed=(Math.imul(seed,31)+ch.charCodeAt(0))>>>0
  const [uploaders,reviewer]=people[department]||[['demo_manager'],'demo_manager']
  const submitted=(Date.UTC(2026,9,1,1,0)+((seed%40)*86400+(seed%7)*1800)*1000)/1000
  return {simulated:true,facts:{
    submitted:{actor:uploaders[seed%uploaders.length],at:submitted},
    reviewed:{actor:reviewer,at:submitted+14400},
    published:{actor:reviewer,at:submitted+16200,automatic:false},
  }}
}
