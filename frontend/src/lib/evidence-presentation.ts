export type EvidenceSource={document_id:string;document_name:string;revision:number;index_token:string;chunk_id:string;text:string;section?:string;risk?:unknown;sources?:unknown;members?:EvidenceSource[]}
export type EvidenceCandidate={candidate_id:string;evidence:EvidenceSource;selectable:boolean;permission_reason?:string}
export function candidateIdentity(candidate:EvidenceCandidate):string {
  const source=candidate.evidence
  const members=source.members?.length?source.members:[source]
  return JSON.stringify(members.map(m=>[m.document_id,m.revision,m.index_token,m.chunk_id]).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))))
}
export function evidenceFiles(candidates:EvidenceCandidate[]){
  const groups=new Map<string,{key:string;source:EvidenceSource;items:Array<{candidate:EvidenceCandidate;rank:number}>}>()
  candidates.forEach((candidate,index)=>{
    const source=candidate.evidence,key=JSON.stringify([source.document_id,source.revision,source.index_token])
    if(!groups.has(key))groups.set(key,{key,source,items:[]})
    groups.get(key)!.items.push({candidate,rank:index+1})
  })
  return [...groups.values()]
}
