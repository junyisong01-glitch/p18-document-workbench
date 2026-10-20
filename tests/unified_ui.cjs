const assert=require('node:assert/strict');
const {P18QaFlow:f}=require('../web/qa/flow.js');
const {P18SourcePreview:p}=require('../web/source-preview.js');
let checks=0;function equal(a,b){assert.deepEqual(a,b);checks++;}
equal(f.steps('retrieving').map(x=>x.state),['active','pending','pending']);
equal(f.steps('selecting').map(x=>x.state),['complete','active','pending']);
equal(f.steps('confirming').map(x=>x.state),['complete','active','pending']);
equal(f.steps('generating').map(x=>x.state),['complete','complete','active']);
equal(f.steps('answered').map(x=>x.state),['complete','complete','complete']);
equal(f.steps('generating',true).map(x=>x.state),['complete','complete','error']);
equal(f.expired({expiresAt:180},179),false);equal(f.expired({expiresAt:180},180),true);equal(f.expired(null,0),true);equal(f.expired({},0),true);
equal(f.sourceView('.pdf',true,[[.1,.1,.2,.2]]),'original');equal(f.sourceView('.pdf',false,[[.1,.1,.2,.2]]),'excerpt');equal(f.sourceView('.pdf',true,[]),'excerpt');equal(f.sourceView('.docx',true,[[.1,.1,.2,.2]]),'excerpt');
equal(p.score(.46875753),'0.4688');equal(p.score(null),'未提供');equal(p.score(NaN),'未提供');equal(p.score('0.4'),'未提供');
// Paint uses validated geometry, no HTML style attributes or executable source text.
class Element{constructor(tag){this.tag=tag;this.children=[];this.style={};this.ownerDocument={createElement:t=>new Element(t)};}append(x){this.children.push(x)}replaceChildren(x){this.children=[x]}setAttribute(k,v){this[k]=v}}
const container=new Element('div');const painted=p.paint(container,'blob:fixture',[[.1,.2,.4,.5],[0,0,2,2]],'虚构PDF');
equal(painted.wrapper.children.length,2);equal(painted.wrapper.children[1].style.left,'10%');equal(painted.image.alt,'虚构PDF');equal(painted.wrapper.children[1].style.height,'30%');
console.log(`${checks} unified UI state/expiry/source assertions passed`);
