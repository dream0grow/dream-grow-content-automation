"""카드뉴스 수동 편집 에디터(editor.html) 생성.

cardnews.py가 만든 cardnews_plan.json + bgs.json 을 읽어, 브라우저에서
미리캔버스/캔바처럼 손으로 고칠 수 있는 단일 HTML 파일을 만든다.

기능: 텍스트 직접 수정(클릭), 글자 크기/굵기/색, 강조색, 폰트 선택 + 폰트 파일 설치,
블록 드래그 이동, 배경 사진/영상 교체, 카드 PNG 내보내기(1080/2160), 전체 내보내기,
수정본 JSON 저장. 인터넷 연결된 브라우저에서 열면 됨(내보내기용 html2canvas CDN).

실행:  python3 -m orchestrator.card_editor --dir <cardnews_out>
"""
import argparse
import json
from pathlib import Path

from orchestrator.cardnews import _css, HANDLE


def build(out_dir: str) -> Path:
    out = Path(out_dir)
    plan = json.loads((out / "cardnews_plan.json").read_text(encoding="utf-8"))
    bgs_fp = out / "bgs.json"
    bgs = json.loads(bgs_fp.read_text(encoding="utf-8")) if bgs_fp.exists() else []
    slides = plan.get("slides", [])
    data = {
        "handle": HANDLE,
        "cover_media": plan.get("cover_media", "photo"),
        "slides": [
            {**s, "bg": (bgs[i] if i < len(bgs) else "")}
            for i, s in enumerate(slides)
        ],
    }
    html = _TEMPLATE.replace("__CARD_CSS__", _css()).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    fp = out / "editor.html"
    fp.write_text(html, encoding="utf-8")
    return fp


_TEMPLATE = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>드림그로우 카드뉴스 에디터</title>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<style>
__CARD_CSS__
/* ---------- 에디터 UI ---------- */
html,body { width:auto; height:auto; }
body { background:#1b1917; font-family:'Pretendard','Apple SD Gothic Neo',sans-serif;
  margin:0; display:flex; min-height:100vh; color:#eee; }
#side { width:230px; padding:16px; background:#242019; overflow-y:auto; }
#side h1 { font-size:15px; color:#ffd21e; margin:0 0 12px; }
.thumb-btn { display:block; width:100%; text-align:left; margin:4px 0; padding:8px 10px;
  background:#332d24; color:#eee; border:1px solid #4a4136; border-radius:8px;
  cursor:pointer; font-size:12px; }
.thumb-btn.on { border-color:#ffd21e; color:#ffd21e; }
#main { flex:1; display:flex; align-items:flex-start; justify-content:center; padding:24px; }
#stagebox { width:594px; height:594px; }
#stage { width:1080px; height:1080px; transform:scale(.55); transform-origin:top left; }
#panel { width:290px; padding:16px; background:#242019; overflow-y:auto; font-size:13px; }
#panel h2 { font-size:13px; color:#ffd21e; margin:16px 0 6px; }
#panel label { display:block; margin:7px 0 2px; color:#bbb; font-size:12px; }
#panel input[type=range] { width:100%; }
#panel select, #panel input[type=text] { width:100%; background:#332d24; color:#eee;
  border:1px solid #4a4136; border-radius:6px; padding:6px; }
.btn { display:inline-block; margin:4px 4px 0 0; padding:8px 12px; background:#ffd21e;
  color:#1b1917; font-weight:800; border:none; border-radius:8px; cursor:pointer; font-size:12px; }
.btn.gray { background:#4a4136; color:#eee; }
.sel { outline:3px dashed #ffd21e !important; outline-offset:4px; }
[contenteditable]:focus { outline:3px solid #6cf; }
.dragging { opacity:.85; }
#stage .wrap, #stage .slogan, #stage .top { cursor:move; }
video.bgvid { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
#hint { font-size:11px; color:#8a7f6d; line-height:1.6; margin-top:10px; }
</style></head><body>
<div id="side"><h1>🖼️ 카드 목록</h1><div id="list"></div>
  <h2 style="color:#ffd21e;font-size:13px;margin-top:14px">전체</h2>
  <button class="btn" onclick="exportAll()">전체 PNG 내보내기</button>
  <button class="btn gray" onclick="savePlan()">수정본 JSON 저장</button>
  <div id="hint">클릭=글자 수정 · 드래그=위치 이동<br>오른쪽 패널=크기/폰트/배경<br>
  내보내기는 인터넷 연결 필요</div></div>
<div id="main"><div id="stagebox"><div id="stage"></div></div></div>
<div id="panel">
  <h2>✏️ 선택한 글자</h2>
  <label>크기 <span id="fsv"></span>px</label><input type="range" id="fs" min="18" max="140" oninput="applySel()">
  <label>굵기</label><select id="fw" onchange="applySel()">
    <option value="500">보통</option><option value="700">굵게</option><option value="800">아주 굵게</option></select>
  <label>글자색</label><input type="color" id="fc" value="#ffffff" oninput="applySel()">
  <h2>🌟 강조색</h2><input type="color" id="hlc" value="#ffd21e" oninput="applyHl()">
  <h2>🔤 폰트</h2>
  <select id="ff" onchange="applyFont()">
    <option value="Pretendard">Pretendard</option>
    <option value="'Noto Sans KR'">Noto Sans KR</option>
    <option value="'Apple SD Gothic Neo'">Apple SD Gothic Neo</option>
    <option value="CustomFont">직접 설치한 폰트</option></select>
  <label>폰트 파일 설치 (.ttf/.otf/.woff2)</label>
  <input type="file" id="fontfile" accept=".ttf,.otf,.woff,.woff2" onchange="installFont(this)">
  <h2>🖼️ 배경</h2>
  <label>사진 교체</label><input type="file" id="bgimg" accept="image/*" onchange="setBgImage(this)">
  <label>영상 넣기 (mp4)</label><input type="file" id="bgvid" accept="video/*" onchange="setBgVideo(this)">
  <button class="btn gray" onclick="clearBg()">배경 지우기</button>
  <h2>⬇️ 이 카드</h2>
  <button class="btn" onclick="exportOne(2)">PNG 저장 (2160px)</button>
  <button class="btn gray" onclick="exportOne(1)">PNG (1080px)</button>
  <div id="hint">영상 배경은 PNG로 안 구워집니다.<br>영상 카드는 인스타 업로드 시 원본 mp4를 쓰세요.</div>
</div>
<script>
const DATA = __DATA__;
let cur = 0, selEl = null;
const stage = document.getElementById('stage');

function rich(t){ return (t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/==(.+?)==/g,'<span class="hl">$1</span>').replace(/\n/g,'<br>'); }

function renderList(){
  const list = document.getElementById('list'); list.innerHTML='';
  DATA.slides.forEach((s,i)=>{
    const b=document.createElement('button'); b.className='thumb-btn'+(i===cur?' on':'');
    b.textContent=(i+1)+'. ['+s.kind+'] '+(s.title||'').replace(/==/g,'').split('\n')[0].slice(0,16);
    b.onclick=()=>{ saveStage(); cur=i; renderSlide(); renderList(); };
    list.appendChild(b);
  });
}

function blockHtml(s,i){
  const total=DATA.slides.length; let step=0;
  for(let k=0;k<=i;k++) if(DATA.slides[k].kind==='content') step++;
  const chip='<span class="chip" contenteditable>'+rich(s.label||'드림그로우')+'</span>';
  const t='<div class="title" contenteditable>'+rich(s.title)+'</div>';
  const b='<div class="body" contenteditable>'+rich(s.body)+'</div>';
  let inner, extra='';
  if(s.kind==='cover'){ inner=chip+t+b; }
  else if(s.kind==='closing'){ inner=chip+t+b;
    extra='<div class="slogan" contenteditable>아이와 부모의 꿈을 키웁니다 · Dream_Grow</div>'; }
  else { inner=chip+'<div class="step" contenteditable>STEP '+String(step).padStart(2,'0')+'</div><div class="rule"></div>'+t+b; }
  return {inner, extra, total};
}

function renderSlide(){
  const s=DATA.slides[cur]; const {inner,extra,total}=blockHtml(s,cur);
  const bg = s.bg ? '<div class="photo" style="background-image:'+s.bg+'"></div>' : '<div class="nophoto"></div>';
  const vid = s.video ? '<video class="bgvid" src="'+s.video+'" autoplay muted loop></video>' : '';
  stage.innerHTML = '<div class="card '+s.kind+'" id="card">'+bg+vid+
    '<div class="scrim"></div>'+
    '<div class="top"><span>'+DATA.handle+'</span><span>'+(cur+1)+' / '+total+'</span></div>'+
    '<div class="wrap" style="'+(s.wrapStyle||'')+'">'+inner+'</div>'+extra+'</div>';
  stage.querySelectorAll('.title,.body,.chip,.step,.slogan').forEach(el=>{
    el.addEventListener('click',e=>{ select(el); e.stopPropagation(); });
  });
  makeDraggable(stage.querySelector('.wrap'));
  const sl=stage.querySelector('.slogan'); if(sl) makeDraggable(sl);
  if(s.styles) Object.entries(s.styles).forEach(([selc,st])=>{
    const el=stage.querySelector(selc); if(el) el.setAttribute('style',(el.getAttribute('style')||'')+st);
  });
}

function select(el){ if(selEl) selEl.classList.remove('sel'); selEl=el; el.classList.add('sel');
  const cs=getComputedStyle(el);
  document.getElementById('fs').value=parseInt(cs.fontSize);
  document.getElementById('fsv').textContent=parseInt(cs.fontSize);
  document.getElementById('fw').value=cs.fontWeight>=800?'800':(cs.fontWeight>=700?'700':'500'); }

function applySel(){ if(!selEl) return;
  const fs=document.getElementById('fs').value;
  document.getElementById('fsv').textContent=fs;
  selEl.style.fontSize=fs+'px';
  selEl.style.fontWeight=document.getElementById('fw').value;
  selEl.style.color=document.getElementById('fc').value; }

function applyHl(){ const c=document.getElementById('hlc').value;
  stage.querySelectorAll('.hl').forEach(e=>e.style.color=c); }

function applyFont(){ const f=document.getElementById('ff').value;
  stage.querySelector('.card').style.fontFamily=f+", 'Noto Sans KR', sans-serif"; }

async function installFont(inp){ const file=inp.files[0]; if(!file) return;
  const buf=await file.arrayBuffer();
  const font=new FontFace('CustomFont',buf); await font.load(); document.fonts.add(font);
  document.getElementById('ff').value='CustomFont'; applyFont();
  alert('폰트 설치 완료: '+file.name); }

function setBgImage(inp){ const f=inp.files[0]; if(!f) return; const r=new FileReader();
  r.onload=e=>{ DATA.slides[cur].bg="url('"+e.target.result+"')"; DATA.slides[cur].video=''; renderSlide(); };
  r.readAsDataURL(f); }

function setBgVideo(inp){ const f=inp.files[0]; if(!f) return;
  DATA.slides[cur].video=URL.createObjectURL(f); renderSlide(); }

function clearBg(){ DATA.slides[cur].bg=''; DATA.slides[cur].video=''; renderSlide(); }

function makeDraggable(el){ if(!el) return; let sx,sy,ox,oy,drag=false;
  el.addEventListener('pointerdown',e=>{
    if(e.target.isContentEditable && e.target!==el) return;
    drag=true; el.classList.add('dragging'); sx=e.clientX; sy=e.clientY;
    const tr=(el.style.transform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/)||[0,0,0]);
    ox=parseFloat(tr[1])||0; oy=parseFloat(tr[2])||0; el.setPointerCapture(e.pointerId); });
  el.addEventListener('pointermove',e=>{ if(!drag) return;
    el.style.transform='translate('+(ox+(e.clientX-sx)/.55)+'px,'+(oy+(e.clientY-sy)/.55)+'px)'; });
  el.addEventListener('pointerup',()=>{ drag=false; el.classList.remove('dragging'); }); }

function saveStage(){ const s=DATA.slides[cur]; const w=stage.querySelector('.wrap');
  if(!w) return; s.wrapStyle=w.getAttribute('style')||'';
  const t=stage.querySelector('.title'), b=stage.querySelector('.body'), c=stage.querySelector('.chip');
  if(t) s.title=t.innerHTML.replace(/<br>/g,'\n').replace(/<span class="hl"[^>]*>(.*?)<\/span>/g,'==$1==').replace(/<[^>]+>/g,'');
  if(b) s.body=b.innerHTML.replace(/<br>/g,'\n').replace(/<span class="hl"[^>]*>(.*?)<\/span>/g,'==$1==').replace(/<[^>]+>/g,'');
  if(c) s.label=c.textContent; }

async function exportOne(scale){ saveStage(); if(selEl) selEl.classList.remove('sel');
  const card=document.getElementById('card');
  stage.style.transform='none';
  const canvas=await html2canvas(card,{scale:scale,useCORS:true,backgroundColor:null});
  stage.style.transform='scale(.55)';
  const a=document.createElement('a');
  a.download='card_'+String(cur+1).padStart(2,'0')+'.png';
  a.href=canvas.toDataURL('image/png'); a.click(); if(selEl) selEl.classList.add('sel'); }

async function exportAll(){ saveStage(); const start=cur;
  for(let i=0;i<DATA.slides.length;i++){ cur=i; renderSlide();
    await new Promise(r=>setTimeout(r,350)); await exportOne(2); }
  cur=start; renderSlide(); renderList(); }

function savePlan(){ saveStage();
  const out={...DATA}; const blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.download='cardnews_plan_edited.json';
  a.href=URL.createObjectURL(blob); a.click(); }

renderList(); renderSlide();
</script></body></html>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="cardnews_plan.json이 있는 출력 폴더")
    a = ap.parse_args()
    print("생성:", build(a.dir))
