import {canonical} from './shared.js';
let sequence=0;
function callNative(message){
 return new Promise((resolve,reject)=>{
  chrome.runtime.sendNativeMessage('com.lingguang.video',{...message,id:++sequence},response=>{
   const error=chrome.runtime.lastError;
   if(error){reject(Error('本机组件未连接。请按安装说明注册桥接组件。'));return;}
   if(response?.error)reject(Error(response.error));else resolve(response?.result);
  });
 });
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id)return false;
 (async()=>{
  if(message.operation==='create')message={...message,url:canonical(message.url)};
  const result=await callNative(message);
  reply({result});
 })().catch(error=>reply({error:error.message}));
 return true;
});
