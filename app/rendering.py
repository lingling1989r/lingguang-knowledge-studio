import html, os, re, shutil, xml.etree.ElementTree as ET
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from PIL import Image
from .store import ROOT

ASSETS = ROOT / "assets"

def text_width(value, font, size):
    cmap = font.getBestCmap()
    return sum(font["hmtx"].metrics[cmap[ord(ch)]][0] for ch in value) * size / font["head"].unitsPerEm

def outline(value, font, size, x, y, color="#111", thick=False):
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    paths = []
    for character in value:
        name = cmap.get(ord(character))
        if name is None:
            raise ValueError("字体不支持文字，请更换题字字体。")
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(pen)
        stroke = f' stroke="{color}" stroke-width="28" stroke-linejoin="round"' if thick else ""
        paths.append(f'<path d="{pen.getCommands()}" transform="translate({x} {y}) scale({scale} {-scale})" fill="{color}"{stroke}/>')
        x += font["hmtx"].metrics[name][0] * scale
    return "".join(paths)

def svg_asset(directory, name, svg):
    import cairosvg
    svg_file = directory / (name + ".svg")
    png_file = directory / (name + ".png")
    svg_file.write_text(svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png_file))
    return png_file

def heading(directory, number, lines):
    font = TTFont(ASSETS / "brush.ttf")
    root = ET.parse(ASSETS / "heading-template.svg").getroot()
    ns = "{http://www.w3.org/2000/svg}"
    defs = next(e for e in root if e.tag == ns + "defs")
    brush = next(e for e in root if e.tag == ns + "path")
    red = next(e for e in root if e.tag == ns + "g" and e.attrib.get("fill") == "#b92c23")
    size = min(108, 900 / max(text_width(v, font, 1) for v in lines))
    start = (1080 - text_width(lines[1], font, size)) / 2
    red.set("transform", f"translate({start + size - 438} 0)")
    chars = "".join(outline(line, font, size, (1080-text_width(line,font,size))/2, baseline, thick=True) for line, baseline in zip(lines, (147,294)))
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="390" viewBox="0 0 1080 390"><title>{html.escape("，".join(lines))}</title><rect width="1080" height="390" fill="white"/>' + ET.tostring(defs, encoding="unicode") + ET.tostring(brush, encoding="unicode") + '<g mask="url(#dry)">' + chars + '</g>' + ET.tostring(red, encoding="unicode") + '</svg>'
    return svg_asset(directory, f"heading-{number:02d}", svg)

def knowledge_graph(directory, nodes):
    candidates = [os.getenv("STUDIO_FONT_PATH", ""), "/System/Library/Fonts/STHeiti Medium.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    path = next((Path(p) for p in candidates if p and Path(p).is_file()), None)
    if path is None:
        raise RuntimeError("未找到中文字体，请配置STUDIO_FONT_PATH。")
    font = TTFont(path, fontNumber=0)
    def label(value, x, y, size=30, color="#494949"):
        size = min(size, 760 / max(text_width(value,font,1),1))
        return outline(value,font,size,x,y,color)
    def center(value, y, size=32, color="#111"):
        return outline(value,font,size,(1080-text_width(value,font,size))/2,y,color)
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1120" viewBox="0 0 1080 1120"><title>本篇干货知识图谱摘要</title><rect width="1080" height="1120" fill="white"/><path d="M80 46 Q480 5 1000 52 L969 133 Q513 105 98 140 Z" fill="#e9eef7"/>' + center("看完这篇，先带走这张图",106,48) + center("核心观点 · 案例启发 · 行动检查",177,29,"#0784ff")
    for i, node in enumerate(nodes):
        y = 222 + i * 186
        svg += f'<rect x="74" y="{y}" width="932" height="154" rx="20" fill="#f4f6fa"/>' + label(f"0{i+1}",103,y+57,42,"#b92c23") + label(node.label,191,y+57,40,"#111") + label(node.point,191,y+97,29) + label(node.check,191,y+133,27,"#0784ff")
        if i < 3:
            svg += f'<path d="M540 {y+161} L540 {y+179} M532 {y+170} L540 {y+179} L548 {y+170}" stroke="#96a4b9" stroke-width="3" fill="none"/>'
    svg += center("来自原视频的案例，结合你的业务表达。",1024,30) + center("记住观点，更要把方法用起来。",1077,33,"#b92c23") + '</svg>'
    return svg_asset(directory, "knowledge-map", svg)

def render_article(job, article, screenshots, source_title):
    directory = Path(job["output_dir"])
    options, prefs = job["options"], job["preferences"]
    entries = []
    def paragraph(text, bold=False):
        entries.append({"kind":"text", "text":text, "bold":bold})
    def image(path, alt):
        entries.append({"kind":"image", "file":path.name, "alt":alt})
    paragraph(article.introduction)
    if options["knowledge_map"]:
        image(knowledge_graph(directory,article.knowledge_map), "干货知识图谱摘要")
    if screenshots:
        image(screenshots[0], "原视频节目画面")
        paragraph("原视频截图 · 来源：" + source_title)
    for value in article.opening:
        paragraph(value)
    for i, section in enumerate(article.sections):
        if options["brush_headings"]:
            image(heading(directory,i+1,section.headline_lines), "，".join(section.headline_lines))
        else:
            entries.append({"kind":"heading", "text":"，".join(section.headline_lines)})
        for value in section.paragraphs:
            paragraph(value)
        if len(screenshots)>i+1:
            image(screenshots[i+1],section.screenshot_caption)
            paragraph(section.screenshot_caption + " · 原视频截图")
    for value in article.closing:
        paragraph(value)
    paragraph(f"我是{prefs['author']}，关注「AI增长破局」，一起把AI用进业务，把营销做得更靠谱。")
    paragraph(f"本文素材来自{job.get('source_author','原视频作者')}《{source_title}》。文章根据原节目内容整理，并加入延伸分析，非逐字转录。")
    rss=options.get("source_type")=="rss"
    platform="YouTube" if job.get("bvid","").startswith("yt-") else "B站"
    entries.append({"kind":"link","text":"打开原节目RSS" if rss else f"点击观看原视频（{platform}）","url":job["url"]})
    if screenshots:paragraph("图片为原视频截图，相关影像版权归原权利人所有。")
    if options["contact_card"]:
        paragraph("想聊个人和小团队的AI营销，扫码添加我的微信，把你的业务问题带过来。")
        paragraph("微信：" + prefs["wechat"],True)
        shutil.copy2(ASSETS / "contact.png",directory/"contact.png")
        shutil.copy2(ASSETS / "contact.svg",directory/"contact.svg")
        image(directory/"contact.png","微信联系卡")
    write_documents(directory,article.title,entries)
    return entries

def write_documents(directory,title,entries):
    markdown = ["# " + title, ""]
    content = ["<h1>"+html.escape(title)+"</h1>"]
    for e in entries:
        if e["kind"]=="image":
            markdown.append(f"![{e['alt']}]({e['file']})")
            content.append(f'<div class="visual"><img src="{html.escape(e["file"])}" alt="{html.escape(e["alt"])}"></div>')
        elif e["kind"]=="link":
            markdown.append(f"[{e['text']}]({e['url']})")
            content.append(f'<p><a href="{html.escape(e["url"])}">{html.escape(e["text"])}</a></p>')
        else:
            text = html.escape(e["text"])
            if e.get("bold"):text="<strong>"+text+"</strong>"
            content.append(("<h2>"+text+"</h2>") if e["kind"]=="heading" else "<p>"+text+"</p>")
            markdown.append(("## " if e["kind"]=="heading" else "") + ("**" if e.get("bold") else "") + e["text"] + ("**" if e.get("bold") else ""))
        markdown.append("")
    css='body{margin:0;color:#494949;background:white;font-family:-apple-system,"PingFang SC",sans-serif}article{max-width:677px;margin:32px auto;padding:0 20px;font-size:17px;line-height:2.02;letter-spacing:.65px}h1{font-size:26px;color:#111;line-height:1.6}h2{font-size:21px;color:#111}p{margin:27px 0}strong{color:#111}img{display:block;width:100%;height:auto}.visual{margin:44px 0 30px}a{color:#0784ff}'
    (directory/"article.html").write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+css+'</style><article>'+"".join(content)+'</article></html>')
    (directory/"article.md").write_text("\n".join(markdown))
