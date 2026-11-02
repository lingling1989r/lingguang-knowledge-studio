export function canonical(value) {
 const text=String(value||'').trim();
 if(/^BV[0-9A-Za-z]{10}$/.test(text))return `https://www.bilibili.com/video/${text}/`;
 let url;try{url=new URL(text);}catch{throw Error('请打开B站视频页，或粘贴完整视频链接。');}
 const match=url.pathname.match(/^\/video\/(BV[0-9A-Za-z]{10})\/?$/);
 if(!['https:','http:'].includes(url.protocol)||!['www.bilibili.com','bilibili.com','m.bilibili.com'].includes(url.hostname)||url.port||url.username||url.password||!match)throw Error('只支持B站视频页或BV号。');
 if(url.searchParams.has('p')&&(url.searchParams.getAll('p').length!==1||url.searchParams.get('p')!=='1'))throw Error('此版本支持当前视频的第1分P，其他分P尚未支持。');
 return `https://www.bilibili.com/video/${match[1]}/`;
}
