const assert=require('node:assert/strict');
const {P18QaFlow:f}=require('../web/qa/flow.js');
const ui=require('../web/qa/interactions.js');let n=0;
function eq(a,b){assert.deepEqual(a,b);n++;}
for(const code of ['session_expired','session_changed','turn_expired','history_invalid','draft_expired','request_failed'])eq(f.recovery(code),{refresh:true,resetSession:true});
for(const code of ['ticket_expired','selection_changed','evidence_stale','config_changed'])eq(f.recovery(code),{refresh:true,resetSession:false});
eq(f.recovery('bad_question'),{refresh:false,resetSession:false});
const turns=[];ui.add(turns,{turn_id:'old',session_id:'expired',answer:'保留旧回答'},'虚构问题',null);
turns[0].detached=true;
ui.add(turns,{turn_id:'fresh',session_id:'new-session',answer:'重新确认后的回答'},'虚构问题',0);
eq(turns.length,1);eq(turns[0].turn_id,'fresh');eq(turns[0].versions.length,2);eq(turns[0].versions[0].answer,'保留旧回答');eq(turns[0].detached,false);
assert.throws(()=>ui.add(turns,{turn_id:'other',session_id:'other'},'虚构问题',0));n++;
turns[0].detached=true;assert.throws(()=>ui.add(turns,{turn_id:'fresh2'},'虚构问题',0));n++;
assert.throws(()=>ui.add(turns,{turn_id:'fresh2',session_id:'fresh2'},'不同问题',0));n++;
console.log(`${n} INT-002 recovery assertions passed`);
