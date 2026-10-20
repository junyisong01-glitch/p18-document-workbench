const assert=require('node:assert/strict');
const {P18QaSessions}=require('../web/qa/sessions.js');
const {P18Splitter}=require('../web/splitter.js');
let checks=0;const eq=(a,b)=>{assert.deepEqual(a,b);checks++};
const store=P18QaSessions.create(),a=store.new();
const stateA={session:'server-a',turns:[{question:'虚构甲负责人',versions:[{answer:'甲'}],active:0}],selected:['a1'],draft:{draft_id:'da'},input:'追问甲'};
store.save(stateA);const b=store.new();store.save({session:'server-b',turns:[{question:'虚构乙接口',versions:[{answer:'60'}],active:0}],selected:['b1'],draft:{draft_id:'db'}});
eq(store.list().length,2);eq(store.current,b.id);eq(store.select(a.id).state.session,'server-a');eq(store.select(a.id).state.selected,['a1']);eq(store.select(a.id).state.draft.draft_id,'da');eq(store.select(a.id).state.input,'追问甲');eq(store.select(b.id).state.turns[0].versions[0].answer,'60');eq(store.list().map(x=>x.active),[true,false]);
stateA.turns[0].versions.push({answer:'甲第二版'});eq(store.select(b.id).state.turns[0].versions.length,1);eq(store.select(a.id).state.turns[0].versions.length,2);
assert.throws(()=>store.select('fake'));checks++;
eq(P18QaSessions.create().list(),[]);eq(store.new().state,null);
eq(P18Splitter.limits(0,1200,260,680,360),260);eq(P18Splitter.limits(900,1200,260,680,360),680);eq(P18Splitter.limits(400,600,260,680,360),260);eq(P18Splitter.limits(400,300,260,680,360),135);
// Shared component uses pointer capture and true container geometry, and keyboard respects bounds.
global.ResizeObserver=class{observe(){}disconnect(){}};
const attributes={},classes=new Set(),handle={setAttribute(k,v){attributes[k]=v},setPointerCapture(){},hasPointerCapture(){return false}},container={getBoundingClientRect(){return {width:1000,left:100,right:1100}},classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)}};let width;
const binding=P18Splitter.bind({handle,container,value:360,side:'left',min:260,max:680,reserve:320,apply:w=>width=w});eq(width,360);
handle.onkeydown({key:'ArrowRight',preventDefault(){}});eq(width,380);handle.onpointerdown({button:0,pointerId:1,preventDefault(){}});handle.onpointermove({clientX:600});eq(width,500);handle.onpointerup({pointerId:1});eq(classes.size,0);handle.onkeydown({key:'Home',preventDefault(){}});eq(width,260);handle.onkeydown({key:'End',preventDefault(){}});eq(width,680);eq(attributes['aria-valuenow'],680);binding.dispose();
let total=0,hiddenWidth;const hiddenContainer={...container,getBoundingClientRect(){return {width:total,left:0,right:total}}};const hidden=P18Splitter.bind({handle:{...handle},container:hiddenContainer,value:360,apply:w=>hiddenWidth=w});eq(hiddenWidth,undefined);total=1000;hidden.resize();eq(hiddenWidth,360);hidden.dispose();
console.log(`${checks} session isolation and shared splitter assertions passed`);
