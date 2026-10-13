"""Fallback for public progressive streams missing from the yt-dlp extractor."""
from urllib.parse import urlparse
import requests
from . import limits

HEADERS={"User-Agent":"Mozilla/5.0","Referer":"https://www.bilibili.com/"}
LIMIT=3*1024*1024*1024

def public_download(bvid, directory, check):
    check()
    response=requests.get("https://api.bilibili.com/x/web-interface/view",params={"bvid":bvid},headers=HEADERS,timeout=30)
    response.raise_for_status(); data=response.json()
    if data.get("code")!=0:raise RuntimeError("B站没有返回可用的视频信息，请检查视频播放权限。")
    info=data["data"]
    limits.duration(info.get("duration"))
    limit=limits.current().max_file_mb*1024**2
    response=requests.get("https://api.bilibili.com/x/player/playurl",params={"bvid":bvid,"cid":info["pages"][0]["cid"],"qn":32,"fnval":0},headers=HEADERS,timeout=30)
    response.raise_for_status(); play=response.json()
    streams=play.get("data",{}).get("durl",[])
    if play.get("code")!=0 or len(streams)!=1:raise RuntimeError("B站未提供可直接读取的视频流，请检查登录或视频权限。")
    url=streams[0]["url"]; host=urlparse(url).hostname or ""
    if urlparse(url).scheme not in ("https","http") or not (host.endswith(".bilivideo.com") or host.endswith(".bilivideo.cn")):
        raise RuntimeError("B站返回的视频流地址无法验证。")
    if streams[0].get("size",0)>limit:raise RuntimeError("视频文件超过当前下载大小上限。")
    target=directory/"source.mp4"; partial=directory/"source.mp4.part"
    try:
        with requests.get(url,headers=HEADERS,stream=True,timeout=(30,60),allow_redirects=False) as response:
            response.raise_for_status()
            if response.is_redirect:raise RuntimeError("视频流发生重定向，请重试。")
            size=0
            with partial.open("wb") as output:
                for chunk in response.iter_content(1024*1024):
                    check(); size+=len(chunk)
                    if size>limit:raise RuntimeError("视频文件超过当前下载大小上限。")
                    output.write(chunk)
        if size==0:raise RuntimeError("B站返回了空的视频文件。")
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return {"title":info["title"],"duration":info["duration"],"uploader":info.get("owner",{}).get("name",""),"id":bvid},target
