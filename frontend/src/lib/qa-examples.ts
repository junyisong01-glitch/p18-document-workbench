import type {Doc,KbId} from './types'
export type QaExample={label:string;question:string}

export function qaExamples(kbId:KbId,documents:Doc[]):QaExample[]{
  // These are question starters, never answers or access grants. Only use
  // current-library readable, published/indexed metadata already in the session.
  const docs=documents.filter(doc=>doc.kbId===kbId&&doc.status==='active'&&doc.indexStatus==='indexed')
  if(!docs.length)return []
  const definitions=kbId==='demo'?[
    {label:'晨间与夜间校准',question:'虚构ZX8的晨间和夜间校准分别需要多长时间？',match:/ZX8.*维护指南/i},
    {label:'校准前的操作',question:'虚构ZX8开始校准前需要执行哪些操作？',match:/ZX8.*维护指南/i},
    {label:'试验台校准周期',question:'虚构星舟QX5试验台的标准模式和节能模式校准周期分别是多少？',match:/QX5.*使用说明/i},
    {label:'L7告警含义',question:'Fictional Lake Beacon的告警代码L7是什么意思？',match:/Fictional.Beacon/i},
  ]:[
    {label:'重复指令对应的缺陷',question:'网络重试使同一条设备指令执行两次，对应什么缺陷？',match:/设备监控平台.*测试报告|QC-RD-TST-001|BUG-2031.*根因/i},
    {label:'E4291含义与处理',question:'E4291表示什么，应该如何处理？',match:/设备监控平台.*接口说明|QC-RD-API-001|接口兼容性核对/i},
    {label:'历史测试结论',question:'设备监控平台V1.3的历史测试结论是什么？',match:/设备监控平台.*测试报告|QC-RD-TST-001/i},
    {label:'设备离线排查',question:'设备在平台上显示离线，应该如何排查？',match:/运维常见问题排查|QC-RD-OPS-001/i},
  ]
  const result=definitions.filter(item=>docs.some(doc=>item.match.test(`${doc.fileName} ${doc.title} ${doc.code}`)))
    .map(({label,question})=>({label,question}))
  // Other departments get prompts about their own visible documents, rather
  // than R&D examples that could reveal inaccessible document names.
  if(!result.length){
    for(const doc of docs.slice(0,2)){
      const title=doc.title||doc.fileName,short=Array.from(title).slice(0,14).join('')
      result.push({label:short+(Array.from(title).length>14?'…':''),question:`《${title}》的适用范围和主要要求是什么？`})
    }
  }
  return result.slice(0,4)
}
