/* Fictional UI state only; no grants, database, storage, or API transport. */
(function (scope) {
  const pages = {'01':'01-home','02':'02-retrieving','03':'03-retrieve-failed','04':'04-evidence-select','05':'05-evidence-detail','06':'06-send-confirm','07':'07-send-confirm-expanded','08':'08-generating','09':'09-request-timeout','10':'10-answer','11':'11-source-panel','12':'12-follow-up','13':'13-status-copy-table'};
  const evidence = [
    {name:'虚构支付接口测试报告.pdf',type:'PDF',text:'测试环境联调时，支付服务返回超时错误，部分测试订单未能正常更新支付状态；该问题只出现在测试环境，尚未发现生产环境受影响。',allowed:true},
    {name:'虚构接口约定.docx',type:'DOC',text:'接口超时时间默认为 3 秒，可按环境配置。',allowed:true},
    {name:'虚构问题排查记录.docx',type:'DOC',text:'团队将测试环境超时调整为 10 秒，并增加请求日志。文档建议增加异步通知校验并设置人工复核机制。',allowed:true},
    {name:'内部联调纪要.docx',type:'DOC',text:'虚构联系人与联调安排，仅供本地演示查看。',allowed:false},
    {name:'旧版接口说明.doc',type:'DOC',text:'旧版接口的超时说明，仅供本地演示查看。',allowed:false},
    {name:'虚构项目基本信息.docx',type:'DOC',text:'项目负责人为林晓岚。项目导师由学院另行指定，现有资料未给出导师姓名。',allowed:true},
    {name:'虚构团队名单.docx',type:'DOC',text:'项目负责人负责协调研发；导师由学院另行指定，不能确定负责人与导师为同一人。',allowed:true}
  ];
  function create() {
    const state={selected:new Set([0,1,2]),follow:false,question:'支付接口测试中出现了哪些问题？',source:0};
    return {
      state,
      enterFollow(){state.follow=true;state.selected=new Set([5,6]);state.question='她同时是导师吗？';},
      reset(){state.follow=false;state.selected=new Set([0,1,2]);state.question='支付接口测试中出现了哪些问题？';state.source=0;},
      select(id,checked){if(!evidence[id]?.allowed)return false;checked?state.selected.add(id):state.selected.delete(id);return true;},
      selected(){return [...state.selected].filter(id=>evidence[id]?.allowed);},
      canConfirm(){return this.selected().length>0;},
      snapshot(){return this.selected().map(id=>({id,...evidence[id]}));}
    };
  }
  const api={pages,evidence,create};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else scope.P18QADemo=api;
})(typeof window==='undefined'?{}:window);
