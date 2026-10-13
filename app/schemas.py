import re
from urllib.parse import urlparse, parse_qs
from pydantic import BaseModel, Field, field_validator, model_validator

BVID = re.compile(r"BV[0-9A-Za-z]{10}")
def canonical_video(value: str) -> tuple[str, str]:
    value = value.strip()
    if BVID.fullmatch(value):
        return value, f"https://www.bilibili.com/video/{value}/"
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ("www.bilibili.com", "bilibili.com", "m.bilibili.com") or parsed.username or parsed.password or parsed.port:
        raise ValueError("请粘贴B站视频页链接或完整BV号，不支持其他网站和短链接。")
    match = re.fullmatch(r"/video/(BV[0-9A-Za-z]{10})/?", parsed.path)
    if not match:
        raise ValueError("链接中没有找到完整BV号，请使用视频页地址。")
    page = parse_qs(parsed.query).get("p", ["1"])
    if page != ["1"]:
        raise ValueError("当前版本支持单个视频的第一分P，请提供对应视频地址。")
    bvid = match[1]
    return bvid, f"https://www.bilibili.com/video/{bvid}/"

class JobRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    source_type: str = "video"
    episode_id: str = Field(default="",max_length=24)
    knowledge_map: bool = True
    screenshots: bool = True
    brush_headings: bool = True
    contact_card: bool = False
    auto_publish: bool = True
    @model_validator(mode="after")
    def valid_source(self):
        from .sources import youtube
        if self.source_type=='rss':
            parsed=urlparse(self.url)
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('RSS须为公开HTTPS地址。')
            if not re.fullmatch(r'[a-f0-9]{24}',self.episode_id):raise ValueError('请先读取RSS并选择单集。')
            self.screenshots=False
        elif self.source_type=='video':
            if (urlparse(self.url).hostname or '') in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):
                self.url=youtube(self.url)[1]
            else:self.url=canonical_video(self.url)[1]
        else:raise ValueError('不支持此来源类型。')
        return self

class Preferences(BaseModel):
    author: str = Field(default="作者", min_length=1, max_length=20)
    wechat: str = Field(default="your-wechat", max_length=40)
    folder: str = Field(default="", max_length=300)
    app_id: str = Field(default="", max_length=100)
    app_secret: str = Field(default="", max_length=300)
    model_config = {"extra": "forbid"}

class Section(BaseModel):
    headline_lines: list[str] = Field(min_length=2, max_length=2)
    paragraphs: list[str] = Field(min_length=2, max_length=5)
    screenshot_time: float = Field(ge=0)
    screenshot_caption: str = Field(max_length=80)

class KnowledgeNode(BaseModel):
    label: str = Field(min_length=1, max_length=6)
    point: str = Field(min_length=1, max_length=25)
    check: str = Field(min_length=1, max_length=25)

class Article(BaseModel):
    title: str = Field(min_length=1, max_length=30)
    introduction: str = Field(min_length=1, max_length=80)
    opening: list[str] = Field(min_length=2, max_length=4)
    sections: list[Section] = Field(min_length=4, max_length=4)
    closing: list[str] = Field(min_length=1, max_length=3)
    knowledge_map: list[KnowledgeNode] = Field(min_length=4, max_length=4)
    summary: str = Field(min_length=1, max_length=1500)
    @field_validator("sections")
    @classmethod
    def headline_limits(cls, sections):
        if any(not 1 <= len(line) <= 10 for section in sections for line in section.headline_lines):
            raise ValueError("毛笔小标题每行必须为1至10个字符")
        return sections
