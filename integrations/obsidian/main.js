const {Plugin,PluginSettingTab,Setting,Modal,Notice,requestUrl,normalizePath}=require('obsidian');
const defaults={endpoint:'http://127.0.0.1:8765',folder:'Lingguang',pending:[],transcripts:true};
class SourceModal extends Modal{constructor(plugin){super(plugin.app);this.plugin=plugin;}onOpen(){const {contentEl}=this;contentEl.createEl('h2',{text:'收集视频到知识库'});let url='';new Setting(contentEl).setName('B站 / YouTube链接').addText(t=>t.onChange(v=>url=v));new Setting(contentEl).addButton(b=>b.setButtonText('提交到本机').setCta().onClick(async()=>{b.setDisabled(true);try{await this.plugin.submit(url);this.close();}catch(e){new Notice(e.message);}finally{b.setDisabled(false);}}));}onClose(){this.contentEl.empty();}}
class HistoryModal extends Modal {
 constructor(plugin){super(plugin.app);this.plugin=plugin;}
 onOpen(){this.render();}
 async render(){
  const el=this.contentEl;el.empty();el.createEl('h2',{text:'任务与历史'});
  el.createEl('p',{text:'本机生成记录；仅点击导入的内容会写入当前知识库。'});
  new Setting(el).addButton(b=>b.setButtonText('刷新').onClick(()=>this.render()));
  try {
   const jobs=await this.plugin.api('/jobs');
   if(!jobs.length)el.createEl('p',{text:'还没有任务，请先收集一个链接。'});
   const names={queued:'排队中',running:'处理中',complete:'已完成',failed:'失败',cancelled:'已取消'};
   for(const job of jobs){
    const row=new Setting(el).setName(job.title||job.bvid||job.url).setDesc((names[job.status]||job.status)+' · '+(job.stage||job.message||'')+(job.error?' · '+job.error:''));
    const action=(label,fn)=>row.addButton(b=>b.setButtonText(label).onClick(async()=>{b.setDisabled(true);try{await fn();await this.render();}catch(e){new Notice(e.message);}finally{b.setDisabled(false);}}));
    if(job.status==='complete')action('导入文章与素材',()=>this.plugin.importJob(job));
    if(['failed','cancelled'].includes(job.status))action('重新提交',()=>this.plugin.submit(job.url));
    if(['queued','running'].includes(job.status))action('取消',()=>this.plugin.api('/jobs/'+encodeURIComponent(job.id)+'/cancel',{}));
    if(job.transcript_available)action('导入完整转录',()=>this.plugin.importTranscript(job));
   }
  }catch(e){el.createEl('p',{text:'无法连接本机服务：'+e.message});}
 }
 onClose(){this.contentEl.empty();}
}
class Settings extends PluginSettingTab{constructor(app,plugin){super(app,plugin);this.plugin=plugin;}display(){this.containerEl.empty();this.containerEl.createEl('p',{text:'此桌面插件连接本机处理程序。无遥测；模型API费用由用户自己的账户承担。'});new Setting(this.containerEl).setName('本机服务地址').setDesc('仅允许127.0.0.1或localhost的HTTP地址。').addText(t=>t.setValue(this.plugin.settings.endpoint).onChange(async v=>{this.plugin.settings.endpoint=v;await this.plugin.saveData(this.plugin.settings);}));new Setting(this.containerEl).setName('自动导入完整转录').setDesc('保留原始机器转录TXT、SRT、JSON，并创建可阅读的转录笔记。').addToggle(t=>t.setValue(this.plugin.settings.transcripts).onChange(async v=>{this.plugin.settings.transcripts=v;await this.plugin.saveData(this.plugin.settings);}));new Setting(this.containerEl).setName('笔记目录').addText(t=>t.setValue(this.plugin.settings.folder).onChange(async v=>{this.plugin.settings.folder=v;await this.plugin.saveData(this.plugin.settings);}));}}
module.exports=class Lingguang extends Plugin{
 async onload(){this.settings={...defaults,...await this.loadData()};this.addSettingTab(new Settings(this.app,this));this.addRibbonIcon('library','任务与历史',()=>new HistoryModal(this).open());this.addCommand({id:'task-history',name:'查看任务与历史',callback:()=>new HistoryModal(this).open()});this.addCommand({id:'collect-source',name:'收集B站或YouTube视频',callback:()=>new SourceModal(this).open()});this.addCommand({id:'import-completed',name:'导入已完成的本机任务',callback:()=>this.sync().catch(e=>new Notice(e.message))});this.registerInterval(window.setInterval(()=>this.sync().catch(()=>{}),5000));}
 base(){const u=new URL(this.settings.endpoint);if(u.protocol!=='http:'||!['127.0.0.1','localhost'].includes(u.hostname)||u.username||u.password||u.search||u.hash||u.pathname!=='/')throw Error('请设置有效的本机HTTP服务地址。');return u.origin;}
 async api(path,body){const base=this.base();const token=(await requestUrl({url:base+'/api/status'})).json.request_token;const r=await requestUrl({url:base+'/api'+path,method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Request-Token':token},...(body===undefined?{}:{body:JSON.stringify(body)}),throw:false});if(r.status>=400)throw Error(r.json&&typeof r.json.detail==='string'?r.json.detail:'本机服务请求失败（'+r.status+'）');return r.json;}
 async submit(url){url=url.trim();if(!url)throw Error('请输入视频链接');const j=await this.api('/jobs',{url,contact_card:false,auto_publish:false});if(!this.settings.pending.includes(j.id))this.settings.pending.push(j.id);await this.saveData(this.settings);new Notice('任务已提交，本机将处理并自动导入完成笔记。');}
 async folder(path){path=String(path||'').replace(/\\/g,'/');if(!path||path.includes(':')||path.split('/').some(x=>x==='..'||x==='.')||path.startsWith('/'))throw Error('笔记目录必须是知识库内的相对路径');let current='';for(const part of normalizePath(path).split('/')){current=current?current+'/'+part:part;if(!this.app.vault.getAbstractFileByPath(current))await this.app.vault.createFolder(current);}return current;}
 async sync(){if(this.syncing)return;this.syncing=true;try{for(const id of [...this.settings.pending]){const j=await this.api('/jobs/'+id);if(j.status==='complete'){await this.importJob(j);this.settings.pending=this.settings.pending.filter(x=>x!==id);await this.saveData(this.settings);}else if(['failed','cancelled'].includes(j.status)){this.settings.pending=this.settings.pending.filter(x=>x!==id);await this.saveData(this.settings);new Notice((j.error||'任务已取消')+'；可在任务与历史中重新提交。');}}}finally{this.syncing=false;}}
 async importJob(job){const root=await this.folder(this.settings.folder);const title=(job.title||job.bvid).replace(/[\\/:*?"<>|\[\]#^]/g,'-').slice(0,80);const path=normalizePath(root+'/'+title+'-'+job.id.slice(0,8)+'.md');if(this.app.vault.getAbstractFileByPath(path)){if(this.settings.transcripts&&job.transcript_available)await this.importTranscript(job);return;}const base=this.base();const r=await requestUrl({url:base+'/api/jobs/'+job.id+'/files/article.md'});let text=r.text;const materials=await this.api('/jobs/'+job.id+'/materials');const folder=await this.folder(root+'/assets/'+job.id);for(const item of materials.files){if(!/^[^/\\]+\.(png|jpg|svg)$/.test(item.name))continue;const out=normalizePath(folder+'/'+item.name);if(!this.app.vault.getAbstractFileByPath(out)){const f=await requestUrl({url:base+'/api/jobs/'+job.id+'/materials/'+encodeURIComponent(item.name)});await this.app.vault.createBinary(out,f.arrayBuffer);}text=text.split(']('+item.name+')').join(']('+out+')');}await this.app.vault.create(path,text+'\n\n来源：'+job.url+'\n');if(this.settings.transcripts&&job.transcript_available)await this.importTranscript(job);new Notice('已导入：'+(job.title||job.id));}
 async importTranscript(job){
  const root=await this.folder(this.settings.folder);
  const dir=await this.folder(root+'/assets/'+job.id);
  const materials=await this.api('/jobs/'+encodeURIComponent(job.id)+'/materials');
  const names=new Set(materials.files.map(f=>f.name));
  if(!names.has('transcript.txt'))throw Error('该任务暂时没有完整转录');
  let transcript='';
  for(const name of ['transcript.txt','transcript.srt','transcript.json']){
   if(!names.has(name))continue;
   const f=await requestUrl({url:this.base()+'/api/jobs/'+encodeURIComponent(job.id)+'/materials/'+name});
   if(name==='transcript.txt')transcript=f.text;
   const path=normalizePath(dir+'/'+name);
   if(!this.app.vault.getAbstractFileByPath(path))await this.app.vault.createBinary(path,f.arrayBuffer);
  }
  const path=normalizePath(root+'/转录-'+job.id+'.md');
  if(!this.app.vault.getAbstractFileByPath(path))await this.app.vault.create(path,'# 完整机器转录\n\n来源：'+job.url+'\n\n'+transcript+'\n');
  new Notice('完整转录已导入');
 }

};
