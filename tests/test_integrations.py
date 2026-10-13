import os, json
from types import SimpleNamespace
import pytest
from integrations import feishu_bot as bot
from app import store

def test_feishu_parses_single_video_and_defaults_to_no_card():
    request=bot.parse_source('帮我收藏 https://youtu.be/dQw4w9WgXcQ')
    assert request.contact_card is False and request.auto_publish is True
    with pytest.raises(ValueError):bot.parse_source('你好')

def test_feishu_rejects_unlisted_sender(monkeypatch):
    monkeypatch.setenv('FEISHU_ALLOWED_OPEN_IDS','ou_owner')
    assert bot.allowed('ou_owner') and not bot.allowed('ou_other')

def test_feishu_message_dedup_does_not_recreate_job(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path)
    monkeypatch.setenv('FEISHU_ALLOWED_OPEN_IDS','ou_owner')
    store.atomic_json(tmp_path/'feishu-events.json',{'om_message':{'status':'submitted','job_id':'test'}})
    from app import server
    monkeypatch.setattr(server,'create_job',lambda *args:pytest.fail('duplicate message'))
    bot.handle('om_message','ou_owner','BV1qG4y187fq')
