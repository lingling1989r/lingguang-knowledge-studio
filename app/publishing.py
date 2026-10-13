import json, re, threading, requests
from PIL import Image
from .store import atomic_json, feishu_config

PUBLISH_LOCK = threading.Lock()

class Feishu:
    def __init__(self, config=None, before_write=None):
        self.before_write=before_write
        self.session = requests.Session()
        self.base = "https://open.feishu.cn/open-apis/"
        config = config or feishu_config()
        if not config.get("app_id") or not config.get("app_secret"):
            raise RuntimeError("请先在发布设置里连接飞书。")
        response = self.session.post(self.base+"auth/v3/tenant_access_token/internal",json=config,timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError("飞书连接验证失败，请检查App ID和App Secret。")
        self.session.headers["Authorization"] = "Bearer " + data["tenant_access_token"]
    def request(self,method,path,**kwargs):
        if self.before_write and method not in ("GET","HEAD"):
            self.before_write()
        response = self.session.request(method,self.base+path,timeout=45,**kwargs)
        response.raise_for_status()
        data = response.json()
        if data.get("code")!=0:
            raise RuntimeError("飞书操作失败：" + str(data.get("msg","未知错误")))
        return data.get("data",{})

def publish(directory,title,entries,folder="",before_write=None):
    with PUBLISH_LOCK:
        return _publish(directory,title,entries,folder,before_write)

def _publish(directory,title,entries,folder,before_write):
    client=Feishu(before_write=before_write)
    manifest_path=directory/"publication.json"
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        doc=manifest["document_id"]
    else:
        data={"title":title}
        if folder:
            match=re.search(r"/folder/([a-zA-Z0-9]+)",folder)
            data["folder_token"]=match[1] if match else folder
        doc=client.request("POST","docx/v1/documents",json=data)["document"]["document_id"]
        manifest={"document_id":doc,"url":"https://feishu.cn/docx/"+doc,"verified":False}
        atomic_json(manifest_path,manifest)
    blocks=[]
    for entry in entries:
        if entry["kind"]=="image":
            blocks.append({"block_type":27,"image":{}})
        else:
            style={"bold":True} if entry.get("bold") else {}
            if entry["kind"]=="link":style["link"]={"url":entry["url"]}
            prop="heading2" if entry["kind"]=="heading" else "text"
            blocks.append({"block_type":4 if prop=="heading2" else 2,prop:{"elements":[{"text_run":{"content":entry["text"],"text_element_style":style}}]}})
    def children():
        return client.request("GET",f"docx/v1/documents/{doc}/blocks/{doc}/children",params={"page_size":500})["items"]
    existing=children()
    if len(existing)>len(blocks):raise RuntimeError("飞书文档内容发生变化，请先检查文档，避免覆盖编辑。")
    for start in range(len(existing),len(blocks),20):
        client.request("POST",f"docx/v1/documents/{doc}/blocks/{doc}/children",json={"children":blocks[start:start+20]})
    current=children()
    for index,entry in enumerate(entries):
        if entry["kind"]!="image" or current[index].get("image",{}).get("token"):continue
        path=directory/entry["file"]
        block=current[index]["block_id"]
        with path.open("rb") as source:
            uploaded=client.request("POST","drive/v1/medias/upload_all",data={"file_name":path.name,"parent_type":"docx_image","parent_node":block,"size":str(path.stat().st_size),"extra":json.dumps({"drive_route_token":doc})},files={"file":(path.name,source,"image/png" if path.suffix==".png" else "image/jpeg")})
        width,height=Image.open(path).size
        client.request("PATCH",f"docx/v1/documents/{doc}/blocks/{block}",json={"replace_image":{"token":uploaded["file_token"],"width":width,"height":height,"align":2}})
    verified=children()
    if len(verified)!=len(blocks) or any(not verified[i].get("image",{}).get("token") for i,e in enumerate(entries) if e["kind"]=="image"):
        raise RuntimeError("飞书图片核验未通过，稿件已保留，可以重试保存。")
    raw=client.request("GET",f"docx/v1/documents/{doc}/raw_content")["content"]
    if "点击观看原视频" not in raw and "打开原节目RSS" not in raw:
        raise RuntimeError("飞书来源说明核验未通过。")
    manifest["verified"]=True
    atomic_json(manifest_path,manifest)
    return manifest["url"]
