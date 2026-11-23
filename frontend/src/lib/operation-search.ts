import {demoIdentityNames} from './demo-identity-names'
export type OperationFilters={actor:string;document:string;mode:'all'|'date'|'range';date:string;start:string;end:string}
export const emptyOperationFilters:OperationFilters={actor:'',document:'',mode:'all',date:'',start:'',end:''}
// These controls always represent Beijing time, independent of the browser timezone.
export function operationSearchParams(filters:OperationFilters){
 const params=new URLSearchParams(),actor=filters.actor.trim(),file=filters.document.trim()
 if(actor){params.set('actor',actor);const accounts=Object.entries(demoIdentityNames).filter(([account,name])=>name.includes(actor)||account.toLowerCase().includes(actor.toLowerCase())).map(([account])=>account);if(accounts.length)params.set('actor_accounts',accounts.join(','))}
 if(file)params.set('document',file)
 let start:number|undefined,end:number|undefined
 if(filters.mode==='date'){
   if(!filters.date)throw new Error('请选择查询日期。')
   start=Date.parse(filters.date+'T00:00:00+08:00')/1000;end=start+86400
 }else if(filters.mode==='range'){
   if(!filters.start.split('T')[0]||!filters.end.split('T')[0])throw new Error('请选择开始和结束时间。')
   start=Date.parse(filters.start+':00+08:00')/1000;end=Date.parse(filters.end+':00+08:00')/1000
   if(start>end)throw new Error('结束时间不能早于开始时间。')
   end+=60 // Include the whole final minute selected by the user.
 }
 if(start!==undefined&&end!==undefined){if(!Number.isFinite(start)||!Number.isFinite(end))throw new Error('日期或时间格式不正确。');params.set('start_at',String(start));params.set('end_at',String(end))}
 return params.toString()
}
