/* 대시보드 프런트엔드 (의존성 없음) */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtTime = (ms) => ms ? new Date(ms).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';
async function api(method, url, body) {
  const r = await fetch(url, { method, headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 2200); }

const STAGE = { queued: ['대기', 'info'], dm_sent: ['DM 발송(클릭 전)', 'info'], awaiting_reply: ['답장 대기', 'warn'], gate_blocked: ['팔로우 대기', 'warn'], delivered: ['전달 완료', 'on'], failed: ['실패', 'err'] };
let status = null;
let media = [];

// ── 라우팅 ────────────────────────────────────────────────────────────
function route() {
  const page = (location.hash || '#dashboard').slice(1).split('?')[0];
  $$('.page').forEach((p) => p.classList.toggle('active', p.id === `page-${page}`));
  $$('.nav a').forEach((a) => a.classList.toggle('active', a.dataset.page === page));
  ({ dashboard: loadDashboard, automations: loadAutomations, leads: loadLeads, settings: loadSettings, connect: loadConnect, logs: loadLogs, bulk: loadBulk, dmmenu: loadDmMenu }[page] || (() => {}))();
}
window.addEventListener('hashchange', route);

// ── 공통 상태 ─────────────────────────────────────────────────────────
async function loadStatus() {
  status = await api('GET', '/api/status');
  const a = status.account;
  $('#accountBox').innerHTML = a
    ? `<b>@${esc(a.username)}</b><span class="muted">${esc(a.name || '')}</span><br><span class="tag">${a.webhook_subscribed ? '웹훅 구독됨' : '웹훅 미구독'}</span> <span class="tag">토큰 ${a.token_days_left ?? '?'}일 남음</span>${status.mock ? ' <span class="tag">MOCK</span>' : ''}`
    : `연결된 계정 없음<br><a href="#connect">→ 인스타그램 연결</a>`;
  $('#masterSwitch').checked = status.settings.master_switch === '1';
  $('#masterLabel').textContent = status.settings.master_switch === '1' ? '켜짐' : '꺼짐';
  return status;
}

// ── 대시보드 ─────────────────────────────────────────────────────────
async function loadDashboard() {
  await loadStatus();
  const t = status.totals;
  const conv = t.gate_blocked ? Math.round((t.gate_converted / t.gate_blocked) * 100) : null;
  $('#statCards').innerHTML = [
    ['자동 DM 발송', t.dm_sent, ''], ['리드마그넷 전달 완료', t.delivered, ''], ['팔로우 게이트 차단', t.gate_blocked, ''],
    ['팔로우 후 전환', t.gate_converted, conv === null ? '' : `<small>전환율 ${conv}%</small>`], ['자동 대댓글', t.comment_replies, ''], ['감지된 댓글', t.comments, ''],
  ].map(([k, v, s]) => `<div class="card"><div class="k">${k}</div><div class="v">${v} ${s}</div></div>`).join('');
  const notes = [];
  if (!status.account) notes.push(`<div class="note">아직 인스타그램 계정이 연결되지 않았습니다. <a href="#connect">연결 페이지</a>에서 연결하세요.</div>`);
  if (status.settings.comment_reply_enabled !== '1') notes.push(`<div class="note">자동 대댓글이 꺼져 있습니다 (경고 감지로 자동 중단되었을 수 있음). 자동 DM 은 계속 작동합니다. <a href="#settings">설정에서 켜기</a></div>`);
  if (status.queue.dm_pending || status.queue.comment_pending) notes.push(`<div class="note ok">대기 중: DM ${status.queue.dm_pending}건 · 대댓글 ${status.queue.comment_pending}건</div>`);
  $('#dashNotes').innerHTML = notes.join('');
  // 차트
  const days = [];
  for (let i = 29; i >= 0; i--) { const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10); days.push(status.daily.find((x) => x.date === d) || { date: d, dm_sent: 0, delivered: 0 }); }
  const max = Math.max(1, ...days.map((d) => d.dm_sent));
  $('#chart').innerHTML = days.map((d) => `<div class="bar" style="height:${Math.round((d.delivered / max) * 100)}%" title="${d.date}: 발송 ${d.dm_sent}, 전달 ${d.delivered}"><i>${d.dm_sent || ''}</i>${[0, 10, 20, 29].includes(days.indexOf(d)) ? `<span>${d.date.slice(5)}</span>` : ''}</div>`).join('');
  $('#chartLegend').textContent = `합계 30일: 발송 ${days.reduce((n, d) => n + (d.dm_sent || 0), 0)} · 전달 ${days.reduce((n, d) => n + (d.delivered || 0), 0)}`;
  renderLog($('#dashLog'), await api('GET', '/api/events?limit=40'));
  loadDiagnostics().catch(() => {});
}

// ── 진단 체크리스트 ──────────────────────────────────────────
async function loadDiagnostics() {
  const d = await api('GET', '/api/diagnostics');
  $('#diagBox').innerHTML = d.checks.map((c) => `<div class="item"><span class="pill ${c.ok ? 'on' : 'warn'}">${c.ok ? '✓' : '!'}</span><span>${esc(c.label)}</span>${c.ok ? '' : `<span class="hint" style="margin-left:8px">${esc(c.hint)}</span>`}</div>`).join('')
    + `<div class="hint" style="margin-top:10px"><b>서버가 확인할 수 없는 항목 (직접 점검)</b><ul style="margin:6px 0 0 16px">${d.manual.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
}
$('#btnDiag').onclick = () => loadDiagnostics().then(() => toast('점검 완료')).catch((e) => toast(e.message));
function kindIcon(m) { if (!m) return '▪'; const k = m.kind || (String(m.media_product_type || '').toUpperCase() === 'REELS' ? 'reels' : 'feed'); return k === 'reels' ? '🎬' : '🖼️'; }
function renderLog(el, events) {
  el.innerHTML = events.length ? events.map((e) => `<div class="item"><span class="time">${fmtTime(e.created_at)}</span><span class="pill ${e.level === 'error' ? 'err' : e.level === 'warn' ? 'warn' : 'info'}">${esc(e.type)}</span><span>${esc(e.message)}</span></div>`).join('') : '<div class="muted">아직 기록이 없습니다.</div>';
}

// ── 자동화 목록 ────────────────────────────────────────────────────────
function previewHtml(a) {
  const btns = (a.buttons || []).map((b) => `<div class="b">${esc(b.label)}</div>`).join('');
  if (a.dm_type === 'text' && !a.follow_gate) return `<div class="bubble text"><div class="body">${esc(a.dm_text)}</div></div>`;
  if (a.dm_type === 'text') return `<div class="bubble"><div class="body">${esc(a.dm_text)}</div><div class="b">${esc(a.buttons?.[0]?.label || '자료 받기')}</div></div>`;
  return `<div class="bubble">${a.image_url ? `<img src="${esc(a.image_url)}" alt="">` : ''}<div class="body"><div class="t">${esc(a.title || a.name)}</div><div class="s">${esc(a.subtitle)}</div></div>${btns}</div>`;
}
async function loadAutomations() {
  await loadStatus();
  const list = await api('GET', '/api/automations');
  const mediaMap = Object.fromEntries((await api('GET', '/api/media').catch(() => [])).map((m) => [String(m.id), m]));
  $('#autoRows').innerHTML = list.length ? list.map((a) => {
    const SCOPE_PILL = { all: '<span class="pill info">전체 게시물</span>', reels: '<span class="pill gate">🎬 릴스 전체</span>', feed: '<span class="pill info">🖼️ 일반 게시물 전체</span>' };
    const posts = SCOPE_PILL[a.post_scope] || ((a.media_ids || []).map((id) => `<div class="trunc" title="${esc(mediaMap[id]?.caption || id)}">${kindIcon(mediaMap[id])} ${esc((mediaMap[id]?.caption || `게시물 ${id}`).slice(0, 32))}</div>`).join('') + (a.apply_to_future ? '<div class="pill info">+ 다음 게시물</div>' : ''));
    const kw = a.keyword_mode === 'any' ? '<span class="pill off">아무 댓글</span>' : (a.keywords || []).map((k) => `<span class="pill gate">${esc(k)}</span>`).join(' ') + ` <span class="hint">(${a.keyword_mode === 'exact' ? '정확히' : '포함'})</span>`;
    return `<tr>
      <td><div style="margin-bottom:6px"><b>${esc(a.name)}</b> ${a.enabled ? '<span class="pill on">켜짐</span>' : '<span class="pill off">꺼짐</span>'} ${a.trigger_type === 'dm' ? '<span class="pill info">DM→DM</span>' : ''}${a.also_dm ? '<span class="pill info">+DM</span>' : ''}</div><div style="margin-bottom:6px">${kw}</div>${posts}</td>
      <td><div class="preview" style="padding:8px">${previewHtml(a)}</div></td>
      <td><div>${a.follow_gate ? '<span class="pill gate">🔒 팔로우 확인</span>' : '<span class="pill off">팔로우 확인 없음</span>'}${(a.cards || []).length ? `<span class="pill info">🎠 캐러셀 ${(a.cards || []).length + 1}장</span>` : ''}${a.send_mode === 'scheduled' ? `<span class="pill warn">⏰ ${fmtTime(a.scheduled_at)} 예약</span>` : ''}</div><div class="hint" style="margin-top:6px">대댓글: ${{ off: 'Off', general: '일반', custom: '특정' }[a.comment_reply_mode]}${a.comment_ai_variation ? ' + AI변형' : ''}</div><div class="hint">발송 ${a.send_count} · 전달 ${a.delivered_count}</div><div class="hint">${fmtTime(a.updated_at)}</div></td>
      <td><div class="row"><button class="btn sm" data-edit="${a.id}">수정</button><button class="btn sm" data-toggle="${a.id}">${a.enabled ? '끄기' : '켜기'}</button><button class="btn sm danger" data-del="${a.id}">삭제</button></div></td></tr>`;
  }).join('') : '<tr><td colspan="4" class="muted">아직 자동화가 없습니다. "+ 자동화 추가"를 눌러 첫 자동화를 만드세요.</td></tr>';
  $$('[data-edit]').forEach((b) => b.onclick = () => openModal(list.find((a) => a.id === Number(b.dataset.edit))));
  $$('[data-toggle]').forEach((b) => b.onclick = async () => { await api('POST', `/api/automations/${b.dataset.toggle}/toggle`); loadAutomations(); });
  $$('[data-del]').forEach((b) => b.onclick = async () => { if (confirm('이 자동화를 삭제할까요?')) { await api('DELETE', `/api/automations/${b.dataset.del}`); toast('삭제됨'); loadAutomations(); } });
}
$('#masterSwitch').onchange = async (e) => { await api('PUT', '/api/settings', { master_switch: e.target.checked ? '1' : '0' }); toast(e.target.checked ? '전체 자동화 켜짐' : '전체 자동화 꺼짐'); loadStatus(); };

// ── 자동화 편집 모달 ───────────────────────────────────────────────────
const form = $('#autoForm');
let editing = null;
function seg(name, value) { $$(`[data-seg="${name}"] button`).forEach((b) => b.classList.toggle('on', b.dataset.v === value)); form.dataset[name] = value; syncDmFields(); }
$$('[data-seg]').forEach((s) => $$('button', s).forEach((b) => b.onclick = () => seg(s.dataset.seg, b.dataset.v)));
const SCOPE_HINT = {
  all: '모든 게시물·릴스에 적용됩니다.',
  reels: '🎬 <b>릴스에만</b> 적용됩니다. 앞으로 올릴 새 릴스에도 자동으로 적용돼요.',
  feed: '🖼️ <b>일반 게시물(사진·캐러셀)에만</b> 적용됩니다. 릴스는 제외돼요.',
  selected: '아래에서 체크한 게시물/릴스에만 적용됩니다.',
};
function syncDmFields() {
  const t = form.dataset.dm_type || 'button';
  $('#cardFields').style.display = t === 'button' ? '' : 'none';
  $('#carouselWrap').style.display = t === 'button' ? '' : 'none';
  $('#textFields').style.display = t === 'text' ? '' : 'none';
  const scope = form.dataset.post_scope || 'all';
  $('#pickerWrap').style.display = scope === 'selected' ? '' : 'none';
  $('#scopeHint').innerHTML = SCOPE_HINT[scope] || '';
  $('#scheduleBox').style.display = form.dataset.send_mode === 'scheduled' ? '' : 'none';
  form.comment_replies.parentElement.querySelector('textarea').style.display = form.dataset.comment_reply_mode === 'custom' ? '' : 'none';
}
function buttonBlock(b = {}, i = 0) {
  const d = document.createElement('div'); d.className = 'btn-block';
  d.innerHTML = `<div class="row between"><b>버튼 ${i + 1}</b><button type="button" class="btn sm danger" data-rm>− 삭제</button></div>
    <div class="row"><input class="input" data-k="label" maxlength="20" placeholder="버튼 레이블 (20자) 예: 수학 개념 로드맵 받기" value="${esc(b.label || '')}" style="max-width:320px"><input class="input" data-k="url" placeholder="(선택) 링크만 있는 버튼이면 URL — 클릭 즉시 이동, 팔로우 확인 불가" value="${esc(b.url || '')}"></div>
    <label class="f" style="font-weight:500">버튼 클릭 시 보내는 메시지 <span class="hint">팔로우 확인을 켜면 팔로워에게만 이 내용이 공개됩니다. [username] 치환 가능, 링크 앞뒤에 공백/줄바꿈. 900자</span></label>
    <textarea class="input" data-k="reply" maxlength="900" placeholder="[username] 님, 신청해 주셔서 감사합니다!&#10;https://drive.google.com/...">${esc(b.reply || '')}</textarea>`;
  d.querySelector('[data-rm]').onclick = () => { d.remove(); renumber(); };
  return d;
}
function renumber() { $$('#buttonsBox .btn-block b').forEach((b, i) => b.textContent = `버튼 ${i + 1}`); $('#btnAddButton').disabled = $$('#buttonsBox .btn-block').length >= 3; }

// ── 캐러셀 추가 카드 (최대 9장 = 첫 카드 포함 10장) ────────────────────────
function cardBlock(c = {}) {
  const d = document.createElement('div'); d.className = 'btn-block card-block';
  d.innerHTML = `<div class="row between"><b class="ct">추가 카드</b><button type="button" class="btn sm danger" data-rm>− 카드 삭제</button></div>
    <div class="row"><input class="input" data-k="title" maxlength="80" placeholder="카드 제목 (80자)" value="${esc(c.title || '')}" style="max-width:320px"><input class="input" data-k="subtitle" maxlength="80" placeholder="부제목 (선택)" value="${esc(c.subtitle || '')}"></div>
    <input class="input" data-k="image_url" placeholder="카드 이미지 URL (선택, 1080×1080 권장)" value="${esc(c.image_url || '')}" style="margin-top:6px">
    <div class="cbtns" style="margin-top:8px"></div>
    <button type="button" class="btn sm" data-addb>+ 이 카드에 버튼 추가 (최대 3개)</button>`;
  const box = d.querySelector('.cbtns');
  const addBtn = (b = {}) => {
    if (box.children.length >= 3) return;
    const e = document.createElement('div'); e.className = 'cbtn';
    e.innerHTML = `<input class="input" data-k="label" maxlength="20" placeholder="버튼 레이블" value="${esc(b.label || '')}" style="max-width:200px">
      <input class="input" data-k="url" placeholder="(선택) 링크만 → 즉시 이동" value="${esc(b.url || '')}" style="max-width:240px">
      <input class="input" data-k="reply" maxlength="900" placeholder="버튼 클릭 시 보낼 메시지 (팔로우 확인 적용)" value="${esc(b.reply || '')}">
      <button type="button" class="btn sm danger" data-rmb>−</button>`;
    e.querySelector('[data-rmb]').onclick = () => e.remove();
    box.appendChild(e);
  };
  (c.buttons || []).forEach(addBtn);
  if (!(c.buttons || []).length) addBtn();
  d.querySelector('[data-addb]').onclick = () => addBtn();
  d.querySelector('[data-rm]').onclick = () => { d.remove(); renumberCards(); };
  return d;
}
function renumberCards() {
  $$('#cardsBox .card-block .ct').forEach((b, i) => b.textContent = `카드 ${i + 2}`);
  $('#btnAddCard').disabled = $$('#cardsBox .card-block').length >= 9;
}
$('#btnAddCard').onclick = () => { if ($$('#cardsBox .card-block').length < 9) { $('#cardsBox').appendChild(cardBlock()); renumberCards(); } };
function readCards() {
  return $$('#cardsBox .card-block').map((d) => ({
    title: $('[data-k="title"]', d).value,
    subtitle: $('[data-k="subtitle"]', d).value,
    image_url: $('[data-k="image_url"]', d).value,
    buttons: $$('.cbtn', d).map((e) => ({ label: $('[data-k="label"]', e).value, url: $('[data-k="url"]', e).value, reply: $('[data-k="reply"]', e).value })).filter((b) => b.label.trim()),
  })).filter((c) => c.title.trim() || c.image_url.trim());
}
$('#btnAddButton').onclick = () => { if ($$('#buttonsBox .btn-block').length < 3) { $('#buttonsBox').appendChild(buttonBlock({}, $$('#buttonsBox .btn-block').length)); renumber(); } };
function readButtons() { return $$('#buttonsBox .btn-block').map((d) => ({ label: $('[data-k="label"]', d).value, url: $('[data-k="url"]', d).value, reply: $('[data-k="reply"]', d).value })).filter((b) => b.label.trim()); }

// 릴스 / 게시물 구분. 서버가 kind 를 넣어주지만 예전 캐시 데이터를 위해 프런트에서도 보정합니다.
function kindOf(m) {
  if (m.kind) return m.kind;
  const pt = String(m.media_product_type || '').toUpperCase();
  if (pt === 'REELS') return 'reels';
  if (pt === 'STORY') return 'story';
  if (pt) return 'feed';
  return String(m.media_type || '').toUpperCase() === 'VIDEO' ? 'reels' : 'feed';
}
const KIND_LABEL = { reels: ['🎬 릴스', 'gate'], feed: ['🖼️ 게시물', 'off'], story: ['📸 스토리', 'info'] };
let mediaFilter = '';   // '' | reels | feed | checked
let mediaQuery = '';
const selectedMedia = new Set();

function updateMediaCount(shown) {
  const nReels = media.filter((m) => kindOf(m) === 'reels').length;
  $('#mediaCount').innerHTML = `전체 ${media.length}개 · <b>🎬 릴스 ${nReels}</b> · 🖼️ 게시물 ${media.length - nReels} · 표시 ${shown} · 선택 <b>${selectedMedia.size}</b>`;
}
function renderMedia() {
  const el = $('#mediaList');
  if (!media.length) {
    el.innerHTML = '<div class="muted" style="padding:8px">게시물이 없습니다. 계정을 연결한 뒤 "새로고침"을 눌러주세요.</div>';
    $('#mediaCount').textContent = '';
    return;
  }
  const q = mediaQuery.trim().toLowerCase();
  const rows = media.filter((m) => {
    if (mediaFilter === 'checked') { if (!selectedMedia.has(String(m.id))) return false; }
    else if (mediaFilter && kindOf(m) !== mediaFilter) return false;
    if (q && !String(m.caption || '').toLowerCase().includes(q)) return false;
    return true;
  });
  el.innerHTML = rows.length ? rows.map((m) => {
    const [label, cls] = KIND_LABEL[kindOf(m)] || ['기타', 'off'];
    const cap = (m.caption || '(캡션 없음)').split('\n')[0].slice(0, 60);
    return `<label class="media-item"><input type="checkbox" value="${esc(m.id)}" ${selectedMedia.has(String(m.id)) ? 'checked' : ''}>`
      + `<img src="${esc(m.thumbnail_url || '')}" onerror="this.style.visibility='hidden'">`
      + `<span class="pill ${cls} kind">${label}</span>`
      + `<span class="cap" title="${esc(m.caption)}">${esc(cap)}</span>`
      + `<span class="hint when">${esc(String(m.timestamp || '').slice(0, 10))}</span></label>`;
  }).join('') : '<div class="muted" style="padding:8px">조건에 맞는 게시물이 없습니다. 필터를 "전체"로 바꿔보세요.</div>';
  $$('#mediaList input[type=checkbox]').forEach((i) => i.onchange = () => {
    if (i.checked) selectedMedia.add(i.value); else selectedMedia.delete(i.value);
    updateMediaCount(rows.length);
  });
  updateMediaCount(rows.length);
}
$$('#mediaTabs .chip').forEach((c) => c.onclick = () => {
  mediaFilter = c.dataset.k;
  $$('#mediaTabs .chip').forEach((x) => x.classList.toggle('on', x === c));
  renderMedia();
});
$('#mediaSearch').oninput = (e) => { mediaQuery = e.target.value; renderMedia(); };
$('#btnMediaRefresh').onclick = async () => {
  const b = $('#btnMediaRefresh'); b.textContent = '불러오는 중...'; b.disabled = true;
  media = await api('GET', '/api/media?refresh=1').catch((e) => { toast('게시물 조회 실패: ' + e.message); return media; });
  b.textContent = '새로고침'; b.disabled = false;
  renderMedia();
  toast(`게시물 ${media.length}개 (릴스 ${media.filter((m) => kindOf(m) === 'reels').length}개) 불러옴`);
};
const readSelectedMedia = () => [...selectedMedia];

async function openModal(a = null) {
  editing = a;
  $('#modalTitle').textContent = a ? `자동화 수정: ${a.name}` : '자동화 추가';
  form.reset(); $('#buttonsBox').innerHTML = ''; $('#previewBox').innerHTML = '';
  const v = a || { trigger_type: 'comment', post_scope: 'all', keyword_mode: 'contains', comment_reply_mode: 'general', dm_type: 'button', send_mode: 'immediate', follow_gate: 1, enabled: 1, buttons: [{ label: '자료 받기', reply: '' }] };
  $('#cardsBox').innerHTML = '';
  form.name.value = v.name || ''; form.also_dm.checked = !!v.also_dm; form.apply_to_future.checked = !!v.apply_to_future;
  form.keywords.value = (v.keywords || []).join(', '); form.comment_replies.value = (v.comment_replies || []).join('\n');
  form.dm_text.value = v.dm_text || ''; form.image_url.value = v.image_url || ''; form.title.value = v.title || ''; form.subtitle.value = v.subtitle || '';
  form.follow_gate.checked = !!v.follow_gate; form.ai_variation.checked = !!v.ai_variation; form.comment_ai_variation.checked = !!v.comment_ai_variation; form.enabled.checked = v.enabled !== 0;
  form.scheduled_at.value = v.scheduled_at ? toLocalInput(v.scheduled_at) : '';
  (v.buttons || []).forEach((b, i) => $('#buttonsBox').appendChild(buttonBlock(b, i))); renumber();
  (v.cards || []).forEach((c) => $('#cardsBox').appendChild(cardBlock(c))); renumberCards();
  seg('trigger_type', v.trigger_type); seg('post_scope', v.post_scope); seg('keyword_mode', v.keyword_mode); seg('comment_reply_mode', v.comment_reply_mode); seg('dm_type', v.dm_type); seg('send_mode', v.send_mode || 'immediate');
  // 선택 상태 초기화 후 목록 렌더
  selectedMedia.clear();
  (v.media_ids || []).forEach((id) => selectedMedia.add(String(id)));
  mediaFilter = ''; mediaQuery = ''; $('#mediaSearch').value = '';
  $$('#mediaTabs .chip').forEach((x) => x.classList.toggle('on', x.dataset.k === ''));
  if (!media.length) media = await api('GET', '/api/media').catch(() => []);
  renderMedia();
  $('#modal').classList.add('open');
}
// datetime-local 은 로컬 시각 문자열을 쓰므로 타임존 보정이 필요합니다.
function toLocalInput(ms) { const d = new Date(Number(ms) - new Date().getTimezoneOffset() * 60000); return d.toISOString().slice(0, 16); }
function fromLocalInput(s) { return s ? new Date(s).getTime() : null; }
function readForm() {
  return {
    name: form.name.value, enabled: form.enabled.checked, trigger_type: form.dataset.trigger_type, also_dm: form.also_dm.checked,
    post_scope: form.dataset.post_scope, media_ids: readSelectedMedia(), apply_to_future: form.apply_to_future.checked,
    keyword_mode: form.dataset.keyword_mode, keywords: form.keywords.value.split(',').map((s) => s.trim()).filter(Boolean),
    comment_reply_mode: form.dataset.comment_reply_mode, comment_replies: form.comment_replies.value.split('\n').map((s) => s.trim()).filter(Boolean),
    dm_type: form.dataset.dm_type, dm_text: form.dm_text.value, image_url: form.image_url.value, title: form.title.value, subtitle: form.subtitle.value,
    buttons: readButtons(), cards: readCards(), follow_gate: form.follow_gate.checked,
    ai_variation: form.ai_variation.checked, comment_ai_variation: form.comment_ai_variation.checked,
    send_mode: form.dataset.send_mode, scheduled_at: fromLocalInput(form.scheduled_at.value),
  };
}
form.onsubmit = async (e) => {
  e.preventDefault();
  const d = readForm();
  if (d.keyword_mode !== 'any' && !d.keywords.length) return toast('키워드를 입력하거나 "불특정"을 선택하세요');
  if (d.post_scope === 'selected' && !d.media_ids.length && !d.apply_to_future) return toast('게시물을 선택하거나 "다음 발행 게시물"을 켜세요');
  if (d.send_mode === 'scheduled' && !d.scheduled_at) return toast('예약 발송 시각을 골라주세요');
  if (d.send_mode === 'scheduled' && d.scheduled_at < Date.now()) return toast('예약 시각은 현재 이후로 잡아주세요');
  if (d.dm_type === 'button' && !d.buttons.length) return toast('버튼을 1개 이상 추가하세요');
  if (d.follow_gate && !d.buttons.some((b) => b.reply.trim())) return toast('팔로우 확인을 쓰려면 버튼에 "클릭 시 메시지"가 있어야 합니다');
  if (editing) await api('PUT', `/api/automations/${editing.id}`, d); else await api('POST', '/api/automations', d);
  $('#modal').classList.remove('open'); toast('저장되었습니다'); loadAutomations();
};
$('#btnPreview').onclick = () => { const d = readForm(); $('#previewBox').innerHTML = `<h2>DM 미리보기</h2><div class="preview">${previewHtml(d)}${d.follow_gate ? `<div class="hint" style="margin-top:8px">🔒 버튼 클릭 → 팔로우 확인 → 팔로워면 아래 메시지 전송:</div><div class="bubble text" style="margin-top:6px"><div class="body">${esc((d.buttons[0]?.reply || d.dm_text || '').replace(/\[username\]/g, '홍길동'))}</div></div><div class="hint" style="margin-top:8px">비팔로워면:</div><div class="bubble" style="margin-top:6px"><div class="body">${esc(status?.settings?.non_follower_message || '')}</div><div class="b">${esc(status?.settings?.follow_retry_button_label || '팔로우했어요.')}</div></div>` : ''}</div>`; };
$('#btnAdd').onclick = () => openModal();
$('#modalClose').onclick = () => $('#modal').classList.remove('open');

// ── 대댓글 문구 풀 ─────────────────────────────────────────────────────
$('#btnPool').onclick = async () => { const pool = await api('GET', '/api/replies-pool'); $('#poolText').value = pool.join('\n'); $('#poolCount').textContent = `${pool.length}개 문구`; $('#poolModal').classList.add('open'); };
$('#poolClose').onclick = () => $('#poolModal').classList.remove('open');
$('#poolText').oninput = () => { $('#poolCount').textContent = `${$('#poolText').value.split('\n').filter((s) => s.trim()).length}개 문구`; };
$('#poolSave').onclick = async () => { const pool = await api('PUT', '/api/replies-pool', { pool: $('#poolText').value.split('\n') }); toast(`${pool.length}개 문구 저장`); $('#poolModal').classList.remove('open'); };

// ── 리드 ─────────────────────────────────────────────────────────────
async function loadLeads() {
  const f = $('#leadFilter').value;
  const rows = (await api('GET', '/api/leads')).filter((r) => !f || r.stage === f);
  $('#leadRows').innerHTML = rows.length ? rows.map((r) => { const [label, cls] = STAGE[r.stage] || [r.stage, 'off']; return `<tr>
    <td><b>${r.username ? '@' + esc(r.username) : '-'}</b><div class="hint">${esc(r.name || '')}</div><div class="mono muted">${esc(r.igsid)}</div></td>
    <td>${esc(r.automation_name || '#' + r.automation_id)}</td>
    <td><span class="pill ${cls}">${label}</span>${r.last_error ? `<div class="hint" style="color:var(--err)">${esc(r.last_error)}</div>` : ''}</td>
    <td>${r.is_follower === 1 ? '<span class="pill on">팔로워</span>' : r.is_follower === 0 ? `<span class="pill warn">미팔로우 (${r.gate_attempts}회 시도)</span>` : '<span class="pill off">미확인</span>'}</td>
    <td class="hint">${esc(r.source)}${r.comment_id ? `<div class="mono">c:${esc(r.comment_id)}</div>` : ''}</td>
    <td class="hint">${fmtTime(r.created_at)}${r.delivered_at ? `<div>전달 ${fmtTime(r.delivered_at)}</div>` : ''}</td></tr>`; }).join('')
    : '<tr><td colspan="6" class="muted">아직 캡처한 리드가 없습니다.</td></tr>';
}
$('#leadFilter').onchange = loadLeads;

// ── 설정 ─────────────────────────────────────────────────────────────
const sform = $('#settingsForm');
async function loadSettings(values) {
  const s = values || await api('GET', '/api/settings');
  // 스토리 멘션에서 재사용할 자동화 목록 채우기
  try {
    const list = await api('GET', '/api/automations');
    $('#storyAutoSel').innerHTML = '<option value="">사용 안 함 (아래 텍스트만 보냄)</option>'
      + list.map((a) => `<option value="${a.id}">#${a.id} ${esc(a.name)}</option>`).join('');
  } catch {}
  for (const el of sform.elements) if (el.name && s[el.name] !== undefined) el.value = s[el.name];
}

// ── 단체 DM ──────────────────────────────────────────────────
let bulkAudience = [];
async function loadBulk() {
  bulkAudience = await api('GET', '/api/bulk/audience').catch(() => []);
  $('#bulkRows').innerHTML = bulkAudience.length ? bulkAudience.map((r) => `<tr>
    <td><input type="checkbox" class="bulkchk" value="${esc(r.igsid)}"></td>
    <td><b>${r.username ? '@' + esc(r.username) : '-'}</b><div class="hint">${esc(r.name || '')}</div></td>
    <td>${fmtTime(r.last_at)}</td>
    <td>${r.minutes_left > 60 ? `${Math.floor(r.minutes_left / 60)}시간 ${r.minutes_left % 60}분` : `${r.minutes_left}분`}</td>
    <td>${r.is_follower ? '<span class="pill on">팔로우</span>' : '<span class="pill off">-</span>'}</td></tr>`).join('')
    : '<tr><td colspan="5" class="muted">최근 24시간 안에 반응한 사람이 없습니다. 버튼을 누르거나 DM 으로 답장한 사람만 대상이 됩니다.</td></tr>';
  $('#bulkHint').textContent = `발송 가능 대상 ${bulkAudience.length}명`;
}
$('#btnBulkRefresh').onclick = () => loadBulk().then(() => toast('대상 갱신됨'));
$('#btnBulkAll').onclick = () => { const all = $$('.bulkchk'); const on = all.some((c) => !c.checked); all.forEach((c) => c.checked = on); };
$('#btnBulkSend').onclick = async () => {
  const igsids = $$('.bulkchk').filter((c) => c.checked).map((c) => c.value);
  if (!igsids.length) return toast('받는 사람을 골라주세요');
  if (!confirm(`${igsids.length}명에게 단체 DM 을 보낼까요? 시간당 전송 제한에 맞춰 순차 발송됩니다.`)) return;
  try {
    const r = await api('POST', '/api/bulk/send', { igsids, text: $('#bulkText').value, button_label: $('#bulkLabel').value, button_url: $('#bulkUrl').value });
    toast(`${r.queued}명 대기열에 등록됨`);
  } catch (e) { toast('실패: ' + e.message); }
};

// ── DM 첫화면 · 고정 메뉴 ───────────────────────────────────────
function iceRow(x = {}) {
  const d = document.createElement('div'); d.className = 'btn-block';
  d.innerHTML = `<div class="row"><input class="input" data-k="question" maxlength="80" placeholder="보이는 질문 (80자) 예: 리드마그넷 어떻게 받나요?" value="${esc(x.question || '')}" style="max-width:340px"><button type="button" class="btn sm danger" data-rm>−</button></div>
    <textarea class="input" data-k="answer" maxlength="900" placeholder="누르면 보낼 답변 (900자, [username] 치환 가능)" style="margin-top:6px">${esc(x.answer || '')}</textarea>`;
  d.querySelector('[data-rm]').onclick = () => d.remove();
  return d;
}
function menuRow(x = {}) {
  const d = document.createElement('div'); d.className = 'btn-block';
  d.innerHTML = `<div class="row"><input class="input" data-k="title" maxlength="20" placeholder="메뉴 이름 (20자)" value="${esc(x.title || '')}" style="max-width:220px"><input class="input" data-k="url" placeholder="(선택) 링크 — 넣으면 클릭 즉시 이동" value="${esc(x.url || '')}"><button type="button" class="btn sm danger" data-rm>−</button></div>
    <textarea class="input" data-k="answer" maxlength="900" placeholder="링크 대신 보낼 답변 (900자)" style="margin-top:6px">${esc(x.answer || '')}</textarea>`;
  d.querySelector('[data-rm]').onclick = () => d.remove();
  return d;
}
async function loadDmMenu() {
  const d = await api('GET', '/api/dm-menu').catch(() => ({ ice_breakers: [], persistent_menu: [] }));
  $('#iceBox').innerHTML = ''; $('#menuBox').innerHTML = '';
  (d.ice_breakers || []).forEach((x) => $('#iceBox').appendChild(iceRow(x)));
  (d.persistent_menu || []).forEach((x) => $('#menuBox').appendChild(menuRow(x)));
  $('#dmMenuHint').textContent = '';
}
$('#btnIceAdd').onclick = () => { if ($$('#iceBox .btn-block').length < 4) $('#iceBox').appendChild(iceRow()); else toast('최대 4개까지'); };
$('#btnMenuAdd').onclick = () => { if ($$('#menuBox .btn-block').length < 5) $('#menuBox').appendChild(menuRow()); else toast('최대 5개까지'); };
$('#btnDmMenuSave').onclick = async () => {
  const ice = $$('#iceBox .btn-block').map((d) => ({ question: $('[data-k="question"]', d).value, answer: $('[data-k="answer"]', d).value })).filter((x) => x.question.trim());
  const menu = $$('#menuBox .btn-block').map((d) => ({ title: $('[data-k="title"]', d).value, url: $('[data-k="url"]', d).value, answer: $('[data-k="answer"]', d).value })).filter((x) => x.title.trim());
  try { await api('PUT', '/api/dm-menu', { ice_breakers: ice, persistent_menu: menu }); toast('인스타그램에 저장됨'); $('#dmMenuHint').textContent = `첫화면 ${ice.length}개 · 고정메뉴 ${menu.length}개 저장됨`; }
  catch (e) { toast('저장 실패: ' + e.message); }
};
sform.onsubmit = async (e) => { e.preventDefault(); const d = {}; for (const el of sform.elements) if (el.name) d[el.name] = el.value; await api('PUT', '/api/settings', d); toast('설정 저장됨'); loadStatus(); };
$('#btnDefaults').onclick = async () => loadSettings(await api('GET', '/api/settings/defaults'));

// ── 연결 ─────────────────────────────────────────────────────────────
async function loadConnect() {
  await loadStatus();
  const a = status.account;
  $('#cfgRedirect').textContent = status.redirect_uri; $('#cfgWebhook').textContent = status.webhook_url;
  $('#cfgDeauth').textContent = `${status.public_url}/auth/instagram/deauthorize`;
  $('#cfgDeletion').textContent = `${status.public_url}/auth/instagram/data-deletion`;
  $('#cfgPrivacy').textContent = `${status.public_url}/privacy`;
  $('#cfgEnv').innerHTML = `IG_APP_ID ${status.app_id_set ? '<span class="pill on">설정됨</span>' : '<span class="pill err">없음</span>'} IG_APP_SECRET ${status.app_secret_set ? '<span class="pill on">설정됨</span>' : '<span class="pill err">없음</span>'} META_APP_SECRET ${status.meta_secret_set ? '<span class="pill on">설정됨</span>' : '<span class="pill warn">없음(권장)</span>'} PUBLIC_URL <span class="mono">${esc(status.public_url)}</span> ${status.polling ? '<span class="pill info">댓글 폴링 ON</span>' : ''} ${status.ai ? '<span class="pill info">AI 변형 가능</span>' : ''}`;
  $('#connectPanel').innerHTML = a ? `
    <div class="row between"><div><b style="font-size:16px">@${esc(a.username)}</b> <span class="muted">${esc(a.name || '')}</span><div class="hint">계정 ID ${esc(a.ig_user_id)} · 팔로워 ${a.followers_count ?? '?'} · 연결 ${fmtTime(a.connected_at)} · 토큰 만료까지 ${a.token_days_left}일</div>
      <div style="margin-top:6px">${a.webhook_subscribed ? '<span class="pill on">웹훅 구독됨 (comments, messages, messaging_postbacks)</span>' : '<span class="pill err">웹훅 미구독</span>'}</div></div>
      <div class="row"><a class="btn" href="/auth/instagram">다시 연결</a><button class="btn" id="btnSub">웹훅 재구독</button><button class="btn" id="btnRefreshTok">토큰 갱신</button><button class="btn danger" id="btnDisc">연결 해제</button></div></div>
    ${status.mock ? '<div class="note">MOCK 모드입니다. 실제 인스타그램 API 를 호출하지 않습니다.</div>' : ''}`
    : `<div class="note">ManyChat 같은 다른 자동 DM 플랫폼과 동시에 사용할 수 없습니다. 연결 전에 다른 서비스와의 연결을 먼저 끊어주세요.</div>
       <a class="btn primary" href="/auth/instagram">Instagram 으로 연결</a> ${status.mock ? '<button class="btn" id="btnMockConnect">모의 계정 연결 (MOCK)</button>' : ''}
       <div class="hint" style="margin-top:8px">권한: 기본 정보 · 메시지 관리 · 댓글 관리. 팔로우 확인은 메시지 관리 권한의 User Profile API 로 이루어집니다.</div>`;
  const on = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
  on('#btnSub', async () => { try { await api('POST', '/api/account/subscribe'); toast('웹훅 구독 완료'); loadConnect(); } catch (e) { toast('실패: ' + e.message); } });
  on('#btnRefreshTok', async () => { const r = await api('POST', '/api/account/refresh-token'); toast(r.refreshed ? '토큰 갱신됨' : '아직 갱신 불가(24시간 미만) 또는 실패'); loadConnect(); });
  on('#btnDisc', async () => { if (confirm('연결을 해제할까요? 자동화 설정은 유지됩니다.')) { await api('POST', '/api/account/disconnect'); loadConnect(); } });
  on('#btnMockConnect', async () => { await api('POST', '/api/mock/connect'); toast('모의 계정 연결됨'); loadConnect(); });
}
$('#btnFollowCheck').onclick = async () => {
  const igsid = $('#fcIgsid').value.trim(); if (!igsid) return;
  try { const r = await api('POST', '/api/tools/follow-check', { igsid }); $('#fcResult').textContent = `${r.is_user_follow_business ? '✅ 이 사용자는 나를 팔로우하고 있습니다' : '🚫 팔로우하지 않습니다'}\n\n` + JSON.stringify(r, null, 2); }
  catch (e) { $('#fcResult').textContent = '오류: ' + e.message; }
};

// ── 로그 ─────────────────────────────────────────────────────────────
async function loadLogs() { renderLog($('#fullLog'), await api('GET', '/api/events?limit=300')); }
$('#btnLogRefresh').onclick = loadLogs;

route();
setInterval(() => { if ((location.hash || '#dashboard') === '#dashboard') loadDashboard().catch(() => {}); }, 30000);
