const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function load(mock){const module={exports:{}};vm.runInNewContext(fs.readFileSync(__dirname+'/main.js','utf8'),{module,require:()=>({Plugin:class{},PluginSettingTab:class{},Modal:class{},Notice:class{},normalizePath:x=>x,requestUrl:mock}),URL,window:{},console});return new module.exports();}
test('only loopback endpoint is accepted',()=>{const p=load();p.settings={endpoint:'http://127.0.0.1:8765'};assert.equal(p.base(),'http://127.0.0.1:8765');p.settings.endpoint='https://example.com';assert.throws(()=>p.base());});
test('imports markdown and images without overwriting a note',async()=>{const files=new Map(),calls=[];const p=load(async r=>{calls.push(r.url);if(r.url.endsWith('/status'))return {json:{request_token:'test'}};if(r.url.endsWith('/materials'))return {status:200,json:{files:[{name:'image.png'},{name:'source.mp4'}]}};if(r.url.endsWith('/article.md'))return {text:'![image](image.png)\nArticle'};return {arrayBuffer:new ArrayBuffer(3)};});p.settings={endpoint:'http://127.0.0.1:8765',folder:'Knowledge'};p.app={vault:{getAbstractFileByPath:x=>files.get(x),createFolder:async x=>files.set(x,'folder'),createBinary:async(x,b)=>files.set(x,b),create:async(x,t)=>files.set(x,t)}};const job={id:'abcdef123456',title:'Test',url:'https://youtube.com/watch?v=abcdefghijk'};await p.importJob(job);await p.importJob(job);assert.match(files.get('Knowledge/Test-abcdef12.md'),/Knowledge\/assets\/abcdef123456\/image.png/);assert.equal(calls.filter(x=>x.endsWith('article.md')).length,1);assert.equal(calls.some(x=>x.endsWith('source.mp4')),false);});

test('imports full transcript attachments and readable note, idempotently',async()=>{
 const files=new Map();
 const p=load(async r=>{
  if(r.url.endsWith('/status'))return {json:{request_token:'test'}};
  if(r.url.endsWith('/materials'))return {status:200,json:{files:['transcript.txt','transcript.srt','transcript.json'].map(name=>({name}))}};
  return {text:'全部原话，不是摘要',arrayBuffer:new ArrayBuffer(8)};
 });
 p.settings={endpoint:'http://localhost:8765',folder:'Knowledge'};
 p.app={vault:{getAbstractFileByPath:x=>files.get(x),createFolder:async x=>files.set(x,'folder'),createBinary:async(x,b)=>files.set(x,b),create:async(x,t)=>files.set(x,t)}};
 const job={id:'job123',url:'https://example.com/source'};
 await p.importTranscript(job);await p.importTranscript(job);
 assert.match(files.get('Knowledge/转录-job123.md'),/全部原话/);
 for(const name of ['transcript.txt','transcript.srt','transcript.json'])assert.ok(files.has('Knowledge/assets/job123/'+name));
});
test('failed jobs leave pending list while import failure stays retryable',async()=>{
 const p=load();p.settings={pending:['fail','done']};p.saveData=async()=>{};
 p.api=async path=>({id:path.split('/').pop(),status:path.endsWith('fail')?'failed':'complete'});
 p.importJob=async()=>{throw Error('disk full');};
 await assert.rejects(()=>p.sync(),/disk full/);
 assert.deepEqual(Array.from(p.settings.pending),['done']);assert.equal(p.syncing,false);
});
test('rejects unsafe vault folder paths',async()=>{
 const p=load();for(const path of ['/tmp','../outside','a/../b','C:/outside','a\\..\\b'])await assert.rejects(()=>p.folder(path));
});
