import json, zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.schemas import canonical_video, JobRequest
from app import store, server, pipeline

@pytest.mark.parametrize("url",["BV1qG4y187fq","https://www.bilibili.com/video/BV1qG4y187fq?spm_id_from=333&vd_source=test","https://bilibili.com/video/BV1qG4y187fq/?p=1"])
def test_real_bilibili_urls_are_canonical(url):
    assert canonical_video(url)==("BV1qG4y187fq","https://www.bilibili.com/video/BV1qG4y187fq/")

@pytest.mark.parametrize("url",["http://127.0.0.1/video/BV1qG4y187fq","https://www.bilibili.com.evil.test/video/BV1qG4y187fq","file:///etc/passwd","https://attacker@www.bilibili.com/video/BV1qG4y187fq","https://www.bilibili.com:8888/video/BV1qG4y187fq","https://www.bilibili.com/video/BV1qG4y187fq/?p=2","https://b23.tv/test"])
def test_non_video_urls_and_other_parts_are_rejected(url):
    with pytest.raises(ValueError):canonical_video(url)

@pytest.fixture
def studio(tmp_path,monkeypatch):
    monkeypatch.setattr(store,"STATE",tmp_path)
    store.atomic_json(tmp_path/"agent.json",{"mode":"gpt"})
    monkeypatch.setenv("OPENAI_API_KEY","test-key-never-returned")
    monkeypatch.setattr(store,"feishu_config",lambda:{"app_id":"test","app_secret":"private-secret"})
    monkeypatch.setattr(pipeline.EXECUTOR,"submit",lambda *args:None)
    with TestClient(server.app,base_url="http://127.0.0.1:8765") as client:
        yield client

def token(client):return {"X-Request-Token":client.get("/api/status").json()["request_token"]}

def test_secrets_are_not_in_status(studio):
    response=studio.get("/api/status")
    assert response.status_code==200
    assert "private-secret" not in response.text and "test-key-never-returned" not in response.text

def test_foreign_origin_and_missing_csrf_cannot_create_jobs(studio):
    assert studio.post("/api/jobs",json={"url":"BV1qG4y187fq"}).status_code==403
    assert studio.post("/api/jobs",headers={**token(studio),"Origin":"https://evil.test"},json={"url":"BV1qG4y187fq"}).status_code==403
    assert studio.get("/api/status",headers={"Host":"evil.test:8765"}).status_code==403

def test_duplicate_running_request_returns_same_job(studio):
    headers=token(studio)
    first=studio.post("/api/jobs",headers=headers,json={"url":"BV1qG4y187fq"}).json()
    second=studio.post("/api/jobs",headers=headers,json={"url":"BV1qG4y187fq"}).json()
    assert first["id"]==second["id"]
    assert len(studio.get("/api/jobs").json())==1

def test_cancelled_job_stops_before_next_stage(studio):
    job=studio.post("/api/jobs",headers=token(studio),json={"url":"BV1qG4y187fq"}).json()
    assert studio.post(f"/api/jobs/{job['id']}/cancel",headers=token(studio)).status_code==200
    with pytest.raises(pipeline.Cancelled):pipeline.check_cancel(job["id"])
    assert studio.get(f"/api/jobs/{job['id']}").json()["status"]=="cancelled"

def test_download_never_includes_internal_transcript_or_publication_state(studio):
    job=store.create(JobRequest(url="BV1qG4y187fq"),store.preferences())
    output=store.job_dir(job["id"])/"output";output.mkdir()
    (output/"article.html").write_text("<p>稿件</p>")
    (output/"publication.json").write_text('{"secret":"private"}')
    (store.job_dir(job["id"])/"transcript-internal.json").write_text("private transcript")
    response=studio.get(f"/api/jobs/{job['id']}/download")
    assert response.status_code==200
    import io
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:assert z.namelist()==["article.html"]
    assert studio.get(f"/api/jobs/{job['id']}/files/publication.json").status_code==404

def test_wrong_contact_identity_cannot_use_saved_personal_card(studio):
    store.save_preferences({"author":"另一位作者","wechat":"someone_else","folder":""})
    response=studio.post("/api/jobs",headers=token(studio),json={"url":"BV1qG4y187fq","contact_card":True})
    assert response.status_code==422


def test_quota_failure_stops_before_scheduling(studio,monkeypatch):
    calls=[]
    monkeypatch.setattr(pipeline.EXECUTOR,"submit",lambda *args:calls.append(args))
    store.atomic_json(store.STATE/"ai-health.json",{"issue":"AI账户额度不足"})
    response=studio.post("/api/jobs",headers=token(studio),json={"url":"BV1qG4y187fq"})
    assert response.status_code==503 and calls==[]

def test_user_cannot_change_platform_ai(studio):
    response=studio.post("/api/settings",headers=token(studio),json={"ai_key":"user-key","ai_model":"other"})
    assert response.status_code==422
    status=studio.get("/api/status").json()
    assert "ai_base" not in status and "ai_model" not in status


def test_management_agent_routes_without_legacy_quota(studio,monkeypatch):
    from app import agent
    store.atomic_json(store.STATE/"ai-health.json",{"issue":"old quota"})
    (store.STATE/"agent.json").unlink()
    monkeypatch.setenv("STUDIO_AGENT_URL","https://agent.example.test/compose")
    monkeypatch.setenv("STUDIO_AGENT_TOKEN","backend-secret")
    calls=[]
    class Response:
        ok=True
        def json(self):return {"article":{"title":"测试文章"}}
    def post(url,**kwargs):
        calls.append((url,kwargs));return Response()
    monkeypatch.setattr(agent.requests,"post",post)
    assert agent.ready()
    content=agent.complete("task-1",{"messages":[{"role":"user","content":"素材"}]},{"type":"object"})
    assert json.loads(content)["title"]=="测试文章"
    assert calls[0][1]["json"]["operation"]=="compose_article"
    assert "backend-secret" not in studio.get("/api/status").text
    assert studio.post("/api/jobs",headers=token(studio),json={"url":"BV1qG4y187fq"}).status_code==202


def admin_login(studio):
    return studio.post('/api/admin/setup',headers=token(studio),json={'password':'a-strong-admin-password'})


def test_admin_requires_login_and_stores_password_hash(studio):
    assert studio.get('/api/admin/overview').status_code==401
    assert admin_login(studio).status_code==200
    auth=(store.STATE/'admin-auth.json').read_text()
    assert 'a-strong-admin-password' not in auth
    assert studio.get('/api/admin/overview').status_code==200
    assert admin_login(studio).status_code==409
    studio.post('/api/admin/logout',headers=token(studio),json={})
    assert studio.get('/api/admin/overview').status_code==401


def test_admin_connection_never_returns_secrets_and_can_switch(studio):
    admin_login(studio)
    data={'mode':'agent','agent_url':'https://agent.example.test/compose','agent_token':'private-agent-secret'}
    assert studio.post('/api/admin/connection',headers=token(studio),json=data).status_code==200
    from app import agent
    assert agent.endpoint()==data['agent_url']
    assert 'private-agent-secret' not in studio.get('/api/admin/overview').text
    assert 'private-agent-secret' not in studio.get('/api/status').text
    assert studio.post('/api/admin/connection',headers=token(studio),json={'mode':'gpt','api_base':'https://api.example.test/v1','model':'default-gpt','api_key':'private-gpt-key'}).status_code==200
    assert agent.endpoint()==''
    assert 'private-gpt-key' not in studio.get('/api/admin/overview').text
    assert (store.STATE/'agent.json').stat().st_mode&0o777==0o600


def test_admin_connection_test_updates_health(studio,monkeypatch):
    from app import agent
    admin_login(studio)
    monkeypatch.setattr(agent,'complete',lambda *args:'{"ok":true}')
    assert studio.post('/api/admin/test',headers=token(studio),json={}).json()['ok'] is True
    assert studio.get('/api/admin/overview').json()['health']['ok'] is True
    monkeypatch.setattr(agent,'complete',lambda *args:'{"unexpected":true}')
    assert studio.post('/api/admin/test',headers=token(studio),json={}).json()['ok'] is False


def test_admin_password_change_invalidates_session(studio):
    admin_login(studio)
    assert studio.post('/api/admin/password',headers=token(studio),json={'password':'another-strong-password'}).status_code==200
    assert studio.get('/api/admin/overview').status_code==401
    assert studio.post('/api/admin/login',headers=token(studio),json={'password':'another-strong-password'}).status_code==200



def test_codex_mode_never_calls_gateway(studio,monkeypatch):
    from app import agent
    store.atomic_json(store.STATE/"agent.json",{"mode":"codex"})
    store.atomic_json(store.STATE/"ai-health.json",{"issue":"old quota"})
    monkeypatch.setattr(agent.shutil,"which",lambda _:"/bin/codex")
    def run(args,**kwargs):
        assert "OPENAI_BASE_URL" not in kwargs["env"]
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "--sandbox" in args and "read-only" in args
        Path(args[args.index("--output-last-message")+1]).write_text('{"ok":true}')
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(agent.subprocess,"run",run)
    monkeypatch.setattr(agent.requests,"post",lambda *a,**k:pytest.fail("gateway must not run"))
    assert agent.ready()
    assert json.loads(agent.complete("test",{"messages":[]},{"type":"object","properties":{"ok":{"type":"boolean"}}}))["ok"]


def test_long_material_preserves_all_chunks(studio,monkeypatch):
    from app import agent
    segments=[{'start':i*120,'end':(i+1)*120,'text':'长视频案例材料内容'*200} for i in range(20)]
    calls=[]
    def complete(job_id,payload,schema):
        chunk=json.loads(payload['messages'][1]['content']);calls.append(chunk)
        return json.dumps({'notes':[{'start':chunk[0]['start'],'end':chunk[-1]['end'],'text':'本段原创要点'}]})
    monkeypatch.setattr(agent,'complete',complete)
    job=store.create(JobRequest(url='BV1qG4y187fq'),store.preferences())
    result=pipeline.compact_material(job,segments)
    assert len(calls)>1
    assert result[0]['start']==0 and result[-1]['end']==2400
    assert sum(len(c) for c in calls)==len(segments)


def test_history_page_and_saved_records_survive_new_client(studio):
    job=store.create(JobRequest(url='BV1qG4y187fq'),store.preferences())
    assert studio.get('/history').status_code==200
    assert '历史生成记录' in studio.get('/history').text
    with TestClient(server.app,base_url='http://127.0.0.1:8765') as second:
        assert any(j['id']==job['id'] for j in second.get('/api/jobs').json())


def test_transcript_export_keeps_timestamps_and_excludes_private_state(studio):
    from app.exports import save_transcript
    import io
    job=store.create(JobRequest(url='BV1qG4y187fq'),store.preferences())
    segments=[{'start':0.25,'end':2.5,'text':'这是测试用户自己的讲话。'}]
    save_transcript(job['id'],segments,{'title':'用户测试','duration':3})
    root=store.job_dir(job['id']);raw=root/'raw';raw.mkdir()
    (raw/'source.mp4').write_bytes(b'test-media')
    (raw/'transcript-internal.json').write_text('private')
    listed=studio.get(f"/api/jobs/{job['id']}/materials").json()['files']
    assert {x['name'] for x in listed}=={'source.mp4','transcript.txt','transcript.srt','transcript.json'}
    assert '00:00:00,250 --> 00:00:02,500' in studio.get(f"/api/jobs/{job['id']}/materials/transcript.srt").text
    assert studio.get(f"/api/jobs/{job['id']}/materials/transcript-internal.json").status_code==404
    r=studio.get(f"/api/jobs/{job['id']}/materials-package")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert 'transcript.txt' in z.namelist() and 'source.mp4' in z.namelist()
        assert 'transcript-internal.json' not in z.namelist()
    assert studio.get(f"/api/jobs/{job['id']}").json()['transcript_available'] is True


def test_public_stream_fallback_downloads_audio_video_source(tmp_path,monkeypatch):
    from app import bilibili
    class Response:
        is_redirect=False
        def __init__(self,data=None):self.data=data
        def raise_for_status(self):pass
        def json(self):return self.data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):yield b'media-data'
    responses=iter([Response({'code':0,'data':{'title':'测试','duration':1852,'pages':[{'cid':123}],'owner':{'name':'用户'}}}),Response({'code':0,'data':{'durl':[{'url':'https://cdn.bilivideo.com/source.mp4','size':10}]}}),Response()])
    monkeypatch.setattr(bilibili.requests,'get',lambda *args,**kwargs:next(responses))
    meta,video=bilibili.public_download('BV1Nrtz6dENu',tmp_path,lambda:None)
    assert meta['duration']==1852 and video.read_bytes()==b'media-data'
    assert not (tmp_path/'source.mp4.part').exists()


def test_limits_block_queue_pause_and_duration(studio):
    from app import limits
    store.atomic_json(store.STATE/'limits.json',{'concurrency':1,'queue_limit':0,'max_video_minutes':30})
    assert studio.post('/api/jobs',headers=token(studio),json={'url':'BV1qG4y187fq'}).status_code==202
    assert studio.post('/api/jobs',headers=token(studio),json={'url':'BV159AUzHEgG'}).status_code==429
    with pytest.raises(RuntimeError):limits.duration(1852)
    limits.duration(1800)
    store.atomic_json(store.STATE/'limits.json',{'accepting_jobs':False})
    assert studio.post('/api/jobs',headers=token(studio),json={'url':'BV159AUzHEgG'}).status_code==503


def test_admin_limits_require_auth_and_busy_concurrency_is_rejected(studio):
    assert studio.post('/api/admin/limits',headers=token(studio),json={}).status_code==401
    admin_login(studio)
    assert studio.post('/api/admin/limits',headers=token(studio),json={'max_video_minutes':60}).status_code==200
    studio.post('/api/jobs',headers=token(studio),json={'url':'BV1qG4y187fq'})
    assert studio.post('/api/admin/limits',headers=token(studio),json={'concurrency':2}).status_code==409
    assert studio.post('/api/admin/limits',headers=token(studio),json={'concurrency':9}).status_code==422


def test_regular_settings_cannot_change_global_feishu_credentials(studio):
    assert studio.post('/api/settings',headers=token(studio),json={'app_id':'new','app_secret':'secret'}).status_code==401


@pytest.mark.parametrize('url',['https://youtu.be/dQw4w9WgXcQ','https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=test','https://youtube.com/shorts/dQw4w9WgXcQ'])
def test_youtube_single_video_canonical_and_store(studio,url):
    request=JobRequest(url=url)
    assert request.url=='https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    assert store.create(request,store.preferences())['bvid']=='yt-dQw4w9WgXcQ'


def test_youtube_channel_rejected():
    with pytest.raises(ValueError):JobRequest(url='https://youtube.com/@channel')


def test_rss_episode_audio_download_and_job(studio,monkeypatch):
    from app import sources
    xml=b'<rss version="2.0"><channel><title>Test Podcast</title><item><title>Episode</title><enclosure url="https://audio.example.test/one.mp3" type="audio/mpeg"/></item></channel></rss>'
    class Response:
        headers={}
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):yield self.data
    monkeypatch.setattr(sources,'fetch',lambda url:Response(xml if 'feed' in url else b'audio'))
    episodes=sources.feed('https://example.test/feed.xml')
    request=JobRequest(url='https://example.test/feed.xml',source_type='rss',episode_id=episodes[0]['id'])
    assert request.screenshots is False
    job=store.create(request,store.preferences());raw=store.job_dir(job['id'])/'raw';raw.mkdir()
    episode,path=sources.podcast_download(job,raw,lambda:None,100)
    assert episode['title']=='Episode' and path.read_bytes()==b'audio'
    listing=studio.post('/api/rss',headers=token(studio),json={'url':request.url}).json()
    assert 'media' not in listing['episodes'][0]


def test_rss_private_addresses_rejected(monkeypatch):
    from app import sources
    monkeypatch.setattr(sources.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError):sources.public_url('https://localhost/feed.xml')


def test_rss_external_entity_xml_is_rejected(monkeypatch):
    from app import sources
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_content(self,size):yield b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss><channel><title>&x;</title></channel></rss>'
    monkeypatch.setattr(sources,'fetch',lambda _:Response())
    with pytest.raises(Exception):sources.feed('https://example.test/feed.xml')
