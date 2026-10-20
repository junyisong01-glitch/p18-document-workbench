const assert=require('node:assert/strict');const ui=require('../web/qa/interactions.js');
assert.equal(ui.width(10,1200),280);assert.equal(ui.width(1000,1200),720);assert.equal(ui.width(500,800),480);
const turns=[];const a={turn_id:'one',answer:'old',citations:[]};ui.add(turns,a,'question',null);
ui.add(turns,{turn_id:'one',answer:'new',citations:[]},'question',0);
assert.equal(turns.length,1);assert.equal(turns[0].versions.length,2);assert.equal(turns[0].versions[0].answer,'old');assert.equal(turns[0].active,1);
assert.throws(()=>ui.add(turns,{turn_id:'other'},'question',0));console.log('QA interactions: 8 assertions passed');
