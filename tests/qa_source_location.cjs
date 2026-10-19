const assert = require('node:assert/strict');
const {P18SourceLocation:{format}} = require('../web/qa/source-location.js');
let count=0;
function test(name,run){run();count++;console.log('PASS '+name);}
const pdf={ext:'.pdf'}, word={ext:'.docx'};
const samePage=[{block_id:'page-1',page:1,label:'第 1 页',raw_start:0,raw_end:10},{block_id:'page-1',page:1,label:'第 1 页',raw_start:12,raw_end:20},{block_id:'page-1',page:1,label:'第 1 页',raw_start:25,raw_end:30}];
test('same PDF page, different raw spans: show once, preserve originals',()=>{
 const chunk={section:'正文',sources:samePage};const before=JSON.stringify(chunk);
 assert.equal(format(pdf,chunk,{pages:2}).text,'PDF · 正文 · 物理第 1 页');assert.equal(JSON.stringify(chunk),before);
});
test('PDF multiple pages: unique and ordered',()=>assert.deepEqual(format(pdf,{sources:[{page:3},{page:1},{page:3}]},{pages:3}).pages,[1,3]));
test('PDF page-like labels are not physical page evidence',()=>assert.equal(format(pdf,{sources:[{label:'第 9 页'}]},{pages:10}).text,'PDF · 未确定物理页码'));
test('PDF without validated page count cannot claim a physical page',()=>assert.equal(format(pdf,{sources:[{page:1}]}).text,'PDF · 未确定物理页码'));
test('PDF invalid/out-of-range pages rejected',()=>assert.deepEqual(format(pdf,{sources:[{page:0},{page:-1},{page:'2'},{page:1.5},{page:9}]},{pages:2}).pages,[]));
test('PDF partly mapped source discloses limitation',()=>assert.match(format(pdf,{sources:[{page:1},{}]},{pages:2}).text,/部分位置未确定物理页码/));
test('DOCX deduplicates section/paragraph and does not use page field',()=>assert.equal(format(word,{section:'安装',sources:[{label:'安装 · 段落 3',page:5},{label:'安装 · 段落 3'}]},{pages:8}).text,'Word · 安装 · 段落 3 · 暂无法确定对应预览页'));
test('DOC reliable explicit original preview page distinguished',()=>assert.equal(format({ext:'.doc'},{section:'请求参数',sources:[{label:'请求参数 · 表格 2',preview_pages:{original:4}}]},{pages:5}).text,'Word · 请求参数 · 表格 2 · 系统转换预览第 4 页'));
test('Word uses existing original block mapping only',()=>{
 const d={ext:'.docx',result:{blocks:[{id:'p1',label:'正文 · 段落 1',preview_pages:{original:2}}]}};
 assert.equal(format(d,{section:'正文',sources:[{block_id:'p1'},{block_id:'p1'}]},{pages:3}).text,'Word · 正文 · 段落 1 · 系统转换预览第 2 页');
});
test('converted-only Word mapping is not original preview page',()=>assert.deepEqual(format(word,{sources:[{preview_pages:{converted:2},label:'第 2 页'}]},{pages:4}).pages,[]));
test('Word out-of-range mapping rejected',()=>assert.match(format(word,{sources:[{preview_pages:{original:8}}]},{pages:3}).text,/暂无法确定对应预览页/));
test('Word unknown/duplicate text mapping does not fabricate pages',()=>assert.equal(format(word,{sources:[{label:'正文 · 表格 1'},{label:'正文 · 表格 1'}]},{pages:5}).text,'Word · 表格 1 · 暂无法确定对应预览页'));
test('Word partial page mapping keeps uncertainty',()=>assert.match(format(word,{sources:[{preview_pages:{original:2}},{label:'段落 3'}]},{pages:3}).text,/部分位置暂无法确定预览页/));
test('Unknown format cannot use PDF or Word page conventions',()=>assert.equal(format({ext:'.txt'},{sources:[{page:1}]},{pages:3}).text,'文档 · 文档级来源'));
test('No source locations are invented from section or plain text',()=>assert.equal(format(word,{section:'第 7 页说明',text:'第 4 页',sources:[]},{pages:10}).text,'Word · 第 7 页说明 · 暂无法确定对应预览页'));
test('Word structural spacing normalizes before deduplication',()=>assert.equal(format(word,{sources:[{label:'段落3'},{label:'段落 3'}]},{pages:1}).text,'Word · 段落 3 · 暂无法确定对应预览页'));
console.log(`${count} source location cases passed`);
