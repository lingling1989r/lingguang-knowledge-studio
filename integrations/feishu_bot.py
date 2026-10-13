"""Single-owner Feishu custom-app bridge; processing stays on this machine."""
import json, os, re, time, hashlib, threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from app import store
from app.schemas import JobRequest
from app.publishing import Feishu

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='feishu-inbox')
SLOTS=threading.BoundedSemaphore(16)

def parse_source(text):
    match=re.search(r'https?://[^\s<>]+|BV[0-9A-Za-z]{10}',text)
    if not match:raise ValueError('请发送B站或YouTube单视频链接；播客请在本机网页选择RSS单集。')
    return JobRequest(url=match[0].rstrip('。，,;'),contact_card=False,auto_publish=True)


def allowed(sender):
    return sender in {x.strip() for x in os.getenv('FEISHU_ALLOWED_OPEN_IDS','').split(',') if x.strip()}


def reply(message_id,text,key):
    Feishu().request('POST',f'im/v1/messages/{message_id}/reply',json={'msg_type':'text','content':json.dumps({'text':text},ensure_ascii=False),'uuid':hashlib.sha256((message_id+key).encode()).hexdigest()[:32]})


def handle(message_id,sender,text):
    if not allowed(sender):return
    seen=store.STATE/'feishu-events.json'
    with store.LOCK:
        records=json.loads(seen.read_text()) if seen.exists() else {}
        if message_id in records:return
        records[message_id]={'status':'received','at':time.time()}
        store.atomic_json(seen,records)
    try:
        from app.server import create_job
        job=create_job(parse_source(text))
        with store.LOCK:
            records=json.loads(seen.read_text());records[message_id].update(status='submitted',job_id=job['id']);store.atomic_json(seen,records)
        reply(message_id,'已接收，正在本机处理。任务：'+job['id'],'accepted')
        while True:
            job=store.read(job['id'])
            if job['status'] in ('failed','cancelled','complete'):
                result='已完成：'+job['title'] if job['status']=='complete' else '处理未完成：'+(job.get('error') or job['message'])
                if job.get('feishu_url'):result+='\n'+job['feishu_url']
                elif job['status']=='complete':result+='\n稿件已保存在本机；飞书保存失败可从后台重试。'
                reply(message_id,result,'result');return
            time.sleep(3)
    except (ValueError,HTTPException) as exc:
        reply(message_id,str(exc.detail) if isinstance(exc,HTTPException) else str(exc),'error')
    except Exception:
        # Do not put provider responses or credentials in chat/logs.
        print('Feishu bridge task failed; inspect local task history. Please resend only after checking the task.')



def receive(data):
    event=data.event
    if event.message.message_type!='text' or event.message.chat_type!='p2p':return
    sender=event.sender.sender_id.open_id
    if not allowed(sender):return
    try:text=json.loads(event.message.content).get('text','')
    except (ValueError,TypeError):return
    def work():
        try:handle(event.message.message_id,sender,text)
        finally:SLOTS.release()
    if SLOTS.acquire(blocking=False):POOL.submit(work)


def main():
    import lark_oapi as lark
    config=store.feishu_config()
    if not config.get('app_id') or not config.get('app_secret'):raise SystemExit('先在本机后台配置飞书自建应用。')
    if not os.getenv('FEISHU_ALLOWED_OPEN_IDS'):raise SystemExit('必须设置FEISHU_ALLOWED_OPEN_IDS，仅接受明确授权的单一账号。')
    owners=[x for x in os.getenv('FEISHU_ALLOWED_OPEN_IDS','').split(',') if x.strip()]
    if len(owners)!=1:raise SystemExit('此版本单用户：每个用户运行自己的实例，仅配置一个open_id。')
    handler=lark.EventDispatcherHandler.builder('','').register_p2_im_message_receive_v1(receive).build()
    client=lark.ws.Client(config['app_id'],config['app_secret'],event_handler=handler,log_level=lark.LogLevel.WARNING)
    threading.Thread(target=client.start,daemon=True,name='feishu-ws').start()
    import uvicorn
    from app.server import app
    uvicorn.run(app,host='127.0.0.1',port=int(os.getenv('STUDIO_PORT','8765'))) 

if __name__=='__main__':main()
