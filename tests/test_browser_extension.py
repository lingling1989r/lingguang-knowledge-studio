import io
import json
import struct
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import store, pipeline
from integrations.browser import native, service, transcription


def test_native_framing_and_size_limit():
    stream=io.BytesIO();native.write_message(stream,{'title':'中文'});stream.seek(0)
    assert native.read_message(stream)=={'title':'中文'}
    with pytest.raises(ValueError):native.read_message(io.BytesIO(struct.pack('=I',native.MAX_MESSAGE+1)))
    assert native.read_message(io.BytesIO()) is None


def test_native_rejects_arbitrary_commands_and_paths(monkeypatch):
    monkeypatch.setattr(native,'ensure_worker',lambda:None)
    with pytest.raises(ValueError):native.dispatch({'operation':'shell','command':'anything'})
    with pytest.raises(ValueError):native.dispatch({'operation':'export','job_id':'../private','format':'transcript.txt'})
    with pytest.raises(ValueError):native.dispatch({'operation':'export','job_id':'a'*32,'format':'../ai.json'})


def test_transcription_request_is_model_api_free_and_deduplicated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path)
    monkeypatch.setattr(transcription,'model_path',lambda:tmp_path)
    monkeypatch.setattr(service.limits,'admission',lambda:None)
    monkeypatch.setattr(service.agent,'ready',lambda:False)
    queued=[];monkeypatch.setattr(pipeline.EXECUTOR,'submit',lambda *args:queued.append(args))
    with TestClient(service.app,base_url='http://127.0.0.1:'+service.PORT) as client:
        token=client.get('/status').json()['request_token'];headers={'X-Request-Token':token}
        body={'url':'https://www.bilibili.com/video/BV1vXJkz1E8U/?spm=test','mode':'transcript'}
        assert client.post('/jobs',json=body).status_code==403
        assert client.post('/jobs',headers={**headers,'Origin':'https://evil.test'},json=body).status_code==403
        first=client.post('/jobs',headers=headers,json=body);assert first.status_code==200, first.text
        second=client.post('/jobs',headers=headers,json=body)
        assert first.json()['id']==second.json()['id'] and len(queued)==1
        assert queued[0][0] is transcription.process
        assert client.post('/jobs',headers=headers,json={**body,'mode':'article'}).status_code==422


def test_transcript_escapes_html_and_preserves_short_words(tmp_path):
    transcription.write_readable(tmp_path,'Title','https://bilibili.com/video/BV1vXJkz1E8U/',[{'start':0,'end':1,'text':'对。<script>alert(1)</script>'}])
    assert '对。' in (tmp_path/'article.md').read_text()
    assert '<script>' not in (tmp_path/'article.html').read_text()


def test_stop_does_not_interrupt_live_jobs(monkeypatch):
    monkeypatch.setattr(native,'ensure_worker',lambda:None)
    monkeypatch.setattr(native,'request',lambda path:[{'status':'running'}])
    with pytest.raises(RuntimeError,match='仍有任务'):native.dispatch({'operation':'stop'})


def test_stop_rejects_mismatched_component_identity(monkeypatch):
    monkeypatch.setattr(native,'ensure_worker',lambda:None)
    monkeypatch.setattr(native,'request',lambda path:[] if path=='/jobs' else {'service':'other','pid':999})
    with pytest.raises(RuntimeError,match='身份'):native.dispatch({'operation':'stop'})
