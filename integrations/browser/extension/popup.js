import {canonical} from './shared.js';
let automatic=true;
const $=id=>document.getElementById(id);
const status={queued:'等待处理',running:'本机处理中',complete:'已完成',failed:'未完成',cancelled:'已取消'};
async function call(value){const response=await chrome.runtime.sendMessage(value);if(response.error)throw Error(response.error);return response.result;}
function notice(text){$('notice').textContent=text;}
async function action(button,fn){button.disabled=true;try{await fn();}catch(error){notice(error.message);}finally{button.disabled=false;}}
async function download(jobId,format){
 const r=await call({operation:'export',job_id:jobId,format});
 const url=new URL(r.download_url);
 if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!/^\/jobs\/[a-f0-9]{32}\/files\/[a-z.-]+$/.test(url.pathname))throw Error('本机返回的下载地址无效');
 await chrome.downloads.download({url:r.download_url,filename:r.filename,saveAs:true});
 notice('已打开浏览器下载，可选择保存位置。');
}
async function refresh(){
 const jobs=await call({operation:'jobs'});$('jobs').replaceChildren();
 if(!jobs.length){const p=document.createElement('p');p.textContent='还没有记录，先转录一个视频。';$('jobs').append(p);}
 for(const job of jobs.slice(0,30)){
  const row=document.createElement('div');row.className='job';
  const title=document.createElement('strong');title.textContent=job.title||job.bvid;
  const state=document.createElement('p');state.textContent=(status[job.status]||job.status)+' · '+(job.message||'')+(job.error?' · '+job.error:'');
  const tools=document.createElement('div');tools.className='tools';
  const button=(text,fn)=>{const b=document.createElement('button');b.textContent=text;b.onclick=()=>action(b,fn);tools.append(b);};
  if(job.transcript_available){for(const [text,format] of [['下载全文','transcript.txt'],['字幕SRT','transcript.srt'],['JSON','transcript.json'],['转录与素材包','materials.zip']])button(text,()=>download(job.id,format));}
  if(job.status==='complete')button('图文包',()=>download(job.id,'article-package.zip'));
  if(job.status==='complete')button('图文MD',()=>download(job.id,'article.md'));
  if(['failed','cancelled'].includes(job.status))button('重新提交',async()=>{await call({operation:'create',url:job.url,mode:job.browser_mode||'transcript'});await refresh();});
  if(['queued','running'].includes(job.status))button('取消',async()=>{await call({operation:'cancel',job_id:job.id});await refresh();});
  if(job.feishu_url){const link=document.createElement('a');link.textContent='打开飞书';link.href=job.feishu_url;link.target='_blank';link.rel='noopener';tools.append(link);}
  row.append(title,state,tools);$('jobs').append(row);
 }
}
async function submit(mode){await call({operation:'create',url:canonical($('url').value),mode,auto_publish:mode==='article'&&$('publish').checked});notice('已提交到本机，关闭弹窗后仍会继续处理。');await refresh();}
$('transcribe').onclick=()=>action($('transcribe'),()=>submit('transcript'));
$('article').onclick=()=>action($('article'),()=>submit('article'));
$('refresh').onclick=()=>action($('refresh'),async()=>{automatic=true;await refresh();});
$('stopWorker').onclick=()=>action($('stopWorker'),async()=>{await call({operation:'stop'});automatic=false;notice('本机组件已停止；重新打开插件或刷新会再次启动。');});
$('config').onsubmit=e=>{e.preventDefault();action(e.submitter,async()=>{await call({operation:'config',config:Object.fromEntries(new FormData(e.target))});e.target.elements.api_key.value='';e.target.elements.app_secret.value='';notice('已保存到本机，密钥不保存在浏览器同步存储中。');});};
$('testModel').onclick=()=>action($('testModel'),async()=>{const r=await call({operation:'test'});notice(r.message);});
$('setup').onclick=()=>chrome.tabs.create({url:chrome.runtime.getURL('help.html')});
(async()=>{
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
 try{$('url').value=canonical(tab?.url);$('videoTitle').textContent=tab?.title||'';}catch{}
 try{await refresh();}catch(error){notice(error.message+' 点击下方“安装帮助”查看配置方法。');}
})();
setInterval(()=>{if(automatic)refresh().catch(()=>{});},5000);
