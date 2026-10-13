"""Canonical video URLs and bounded public podcast RSS retrieval."""
import hashlib, ipaddress, socket, re
from urllib.parse import urlparse, urljoin, parse_qs
import requests
from defusedxml import ElementTree


def youtube(value):
    p=urlparse(value); host=p.hostname
    if p.scheme not in ('http','https') or p.username or p.password or p.port:raise ValueError('请提供有效的视频链接。')
    if host=='youtu.be':vid=p.path.strip('/')
    elif host in ('youtube.com','www.youtube.com','m.youtube.com'):
        if p.path=='/watch':vid=parse_qs(p.query).get('v',[''])[0]
        else:
            match=re.fullmatch(r'/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})/?',p.path);vid=match[1] if match else ''
    else:raise ValueError('请提供 B站或 YouTube 视频链接。')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',vid):raise ValueError('未找到有效的 YouTube 视频标识，不支持频道和播放列表。')
    return vid,'https://www.youtube.com/watch?v='+vid


def public_url(value):
    p=urlparse(value)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('RSS及媒体须使用公开 HTTPS 地址。')
    try:addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
    except OSError:raise ValueError('无法解析RSS或媒体地址。')
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('不支持内网或本机地址。')
    return value


def fetch(url):
    for _ in range(5):
        public_url(url)
        r=requests.get(url,stream=True,timeout=(20,60),allow_redirects=False,headers={'User-Agent':'ContentStudio/1.0'})
        if r.is_redirect:
            next_url=urljoin(url,r.headers['Location']);r.close();url=next_url;continue
        r.raise_for_status();return r
    raise RuntimeError('RSS或媒体重定向次数过多。')


def feed(url):
    with fetch(url) as response:
        body=bytearray()
        for part in response.iter_content(65536):
            body.extend(part)
            if len(body)>2*1024*1024:raise ValueError('RSS超过2MiB解析上限。')
    root=ElementTree.fromstring(body)
    channel=root.find('channel')
    if channel is None:raise ValueError('请提供播客 RSS 2.0 地址，不是节目网页。')
    result=[]
    for item in channel.findall('item')[:100]:
        enclosure=item.find('enclosure')
        if enclosure is None or not enclosure.get('url'):continue
        media=urljoin(url,enclosure.get('url'))
        result.append({'id':hashlib.sha256(media.encode()).hexdigest()[:24],'title':item.findtext('title') or '未命名单集','media':media,'date':item.findtext('pubDate') or '', 'author':channel.findtext('title') or '播客作者'})
    if not result:raise ValueError('此RSS没有包含可下载的单集 enclosure。')
    return result


def podcast_download(job,directory,check,max_bytes):
    episodes=feed(job['url']);episode=next((e for e in episodes if e['id']==job['options'].get('episode_id')),None)
    if episode is None:raise RuntimeError('RSS单集已不存在，请重新选择单集。')
    target=directory/'source.m4a'; partial=directory/'source.m4a.part'
    try:
        with fetch(episode['media']) as r:
            if int(r.headers.get('Content-Length','0'))>max_bytes:raise RuntimeError('播客文件超过下载大小上限。')
            count=0
            with partial.open('wb') as output:
                for chunk in r.iter_content(1024*1024):
                    check();count+=len(chunk)
                    if count>max_bytes:raise RuntimeError('播客文件超过下载大小上限。')
                    output.write(chunk)
        if not count:raise RuntimeError('播客返回空媒体文件。')
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True);raise
    return episode,target
