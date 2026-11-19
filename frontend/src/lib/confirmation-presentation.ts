export type Message = {role:string;content:string}
export type WireSource = {
  id?:string; document_name?:string; section?:unknown; revision?:number;
  text?:string; risk?:unknown; members?:WireSource[]; [key:string]:unknown
}
export function parseConfirmation(messages:unknown):{
  question:string; systems:string[]; evidence:WireSource[]; history:unknown[]
}|null {
  // Presentation only. The original messages and server ticket remain untouched.
  if(!Array.isArray(messages)||messages.length!==2||messages[0]?.role!=='system'||messages[1]?.role!=='user'
    ||messages.some(message=>typeof message.content!=='string'))return null
  try {
    const payload=JSON.parse(messages[1].content)
    if(typeof payload.question!=='string'||!Array.isArray(payload.untrusted_evidence)
      ||!Array.isArray(payload.history_for_reference_only))return null
    if(payload.untrusted_evidence.some((source:WireSource)=>!source||typeof source!=='object'
      ||typeof source.text!=='string'||(source.members!==undefined&&(!Array.isArray(source.members)
        ||source.members.some(member=>!member||typeof member!=='object'||(member.text!==undefined&&typeof member.text!=='string'))))))return null
    return {question:payload.question,systems:[messages[0].content],evidence:payload.untrusted_evidence,history:payload.history_for_reference_only}
  } catch {return null}
}
export function isLocalAnswerEndpoint(endpoint:unknown):boolean {
  return endpoint==='http://localhost:11434/api/chat'||endpoint==='http://127.0.0.1:11434/api/chat'
}
export function endpointHost(endpoint:unknown):string {
  try{return new URL(String(endpoint)).host}catch{return String(endpoint||'接收地址未提供')}
}
export function displayValue(value:unknown):string {
  if(value===undefined||value===null)return ''
  return typeof value==='string'?value:JSON.stringify(value,null,2)
}
