// HTTP 서버: 웹훅 · OAuth 연결 · 대시보드 API · 정적 파일
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { config, ROOT, redirectUri, webhookUrl } from './config.js';
import {
  db, now, logEvent, getAccount, getSettings, setSettings, listAutomations, getAutomation, saveAutomation, DEFAULT_SETTINGS,
} from './db.js';
import { authorizeUrl, exchangeCode, exchangeLongLived, clientFor, mockState } from './instagram.js';
import { verifyChallenge, validSignature, dispatch, eventKey } from './webhook.js';
import { startQueues, tick, queueStatus, pendingCount } from './queues.js';
import { startPoller, pollOnce } from './poller.js';
import { startTokenRefresher, refreshIfNeeded } from './tokens.js';
import { loadReplyPool, saveReplyPool } from './text.js';
import { upsertMedia, buildFirstMessage } from './automation.js';

const PUBLIC_DIR = path.join(ROOT, 'public');
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };

// ── 유틸 ─────────────────────────────────────────────────────────────────
function json(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(data));
}
function text(res, status, body, type = 'text/plain; charset=utf-8') { res.writeHead(status, { 'Content-Type': type }); res.end(body); }
function redirect(res, to) { res.writeHead(302, { Location: to }); res.end(); }
function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => { chunks.push(c); if (chunks.reduce((n, b) => n + b.length, 0) > 2e6) { reject(new Error('body too large')); req.destroy(); } });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}
function authorized(req) {
  if (!config.dashboardPassword) return true; // 비밀번호 미설정 시 인증 없음 (로컬 개발용)
  const h = req.headers.authorization || '';
  if (!h.startsWith('Basic ')) return false;
  const [, pw = ''] = Buffer.from(h.slice(6), 'base64').toString('utf8').split(':');
  const a = Buffer.from(pw), b = Buffer.from(config.dashboardPassword);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}
const oauthStates = new Map();

// Meta signed_request (base64url(sig).base64url(json)) 해석
function parseSignedRequest(body) {
  try {
    const params = new URLSearchParams(body);
    const sr = params.get('signed_request') || (body.startsWith('{') ? JSON.parse(body).signed_request : null);
    if (!sr) return null;
    const [sig, payload] = sr.split('.');
    const data = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    if (config.appSecret) {
      const expected = crypto.createHmac('sha256', config.appSecret).update(payload).digest('base64url');
      if (expected !== sig) return null;
    }
    return data;
  } catch { return null; }
}

const PRIVACY_TEXT = `개인정보 처리방침 (Instagram AutoDM)

이 서버는 운영자 본인의 Instagram 프로페셔널 계정에 달린 댓글과 DM 이벤트를 받아 자동 응답을 보냅니다.
수집 항목: 댓글/메시지를 보낸 사용자의 Instagram-scoped ID, 사용자 이름, 댓글 내용, 팔로우 여부.
이용 목적: 요청한 자료(리드마그넷) 전달 및 대시보드 통계.
보관: 운영자 서버의 SQLite 데이터베이스. 제3자 제공 없음.
삭제 요청: Instagram 앱 설정 > 웹사이트 허가 에서 이 앱을 제거하면 보관된 기록이 삭제됩니다 (${config.publicUrl}/auth/instagram/data-deletion).
문의: 운영자 Instagram 프로필 DM.`;

// ── 계정 저장 ─────────────────────────────────────────────────────────────
async function connectAccount(code) {
  const short = await exchangeCode(code);
  const long = await exchangeLongLived(short.access_token);
  const tmp = clientFor({ access_token: long.access_token, ig_user_id: 'me' });
  const me = await tmp.getMe();
  const igId = String(me.user_id || me.id);
  db.prepare(`INSERT INTO accounts(ig_user_id, app_scoped_id, username, name, profile_picture_url, followers_count, access_token, token_expires_at, connected_at, updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(ig_user_id) DO UPDATE SET app_scoped_id = excluded.app_scoped_id, username = excluded.username, name = excluded.name, profile_picture_url = excluded.profile_picture_url,
      followers_count = excluded.followers_count, access_token = excluded.access_token, token_expires_at = excluded.token_expires_at, connected_at = excluded.connected_at, updated_at = excluded.updated_at`)
    .run(igId, String(me.id || ''), me.username || '', me.name || '', me.profile_picture_url || '', me.followers_count ?? null, long.access_token, now() + (long.expires_in || 5184000) * 1000, now(), now());
  // 다른 계정 레코드는 제거 (슬롯 1개)
  db.prepare('DELETE FROM accounts WHERE ig_user_id != ?').run(igId);
  const account = getAccount();
  try {
    await clientFor(account).subscribeWebhooks();
    db.prepare('UPDATE accounts SET webhook_subscribed = 1 WHERE id = ?').run(account.id);
  } catch (e) { logEvent('warn', 'subscribe', `웹훅 구독 실패: ${e.message}`); }
  logEvent('info', 'connected', `인스타그램 연결 완료: @${me.username} (${igId})`);
  return getAccount();
}

function publicAccount(a) {
  if (!a) return null;
  const { access_token, ...rest } = a;
  return { ...rest, token_days_left: a.token_expires_at ? Math.floor((a.token_expires_at - now()) / 86400000) : null };
}

// ── API 라우팅 ────────────────────────────────────────────────────────────
async function api(req, res, url) {
  const m = req.method;
  const p = url.pathname;
  const body = ['POST', 'PUT', 'PATCH'].includes(m) ? (JSON.parse((await readBody(req)).toString('utf8') || '{}')) : null;
  const seg = p.split('/').filter(Boolean); // ['api', ...]

  if (p === '/api/status' && m === 'GET') {
    const account = getAccount();
    const stats7 = db.prepare('SELECT * FROM stats_daily WHERE date >= ? ORDER BY date').all(new Date(now() - 29 * 86400000).toISOString().slice(0, 10));
    const totals = db.prepare('SELECT COALESCE(SUM(dm_sent),0) dm_sent, COALESCE(SUM(delivered),0) delivered, COALESCE(SUM(gate_blocked),0) gate_blocked, COALESCE(SUM(gate_converted),0) gate_converted, COALESCE(SUM(comment_replies),0) comment_replies, COALESCE(SUM(comments),0) comments FROM stats_daily').get();
    return json(res, 200, {
      account: publicAccount(account), settings: getSettings(), queue: queueStatus(), totals, daily: stats7,
      automations: listAutomations().length, mock: config.mock, public_url: config.publicUrl, webhook_url: webhookUrl(), redirect_uri: redirectUri(),
      app_id_set: !!config.appId, app_secret_set: !!config.appSecret, meta_secret_set: !!config.metaAppSecret, polling: config.commentPolling, ai: !!config.anthropicKey,
    });
  }
  if (p === '/api/settings' && m === 'GET') return json(res, 200, getSettings());
  if (p === '/api/settings' && m === 'PUT') { setSettings(body); logEvent('info', 'settings', '설정 저장'); return json(res, 200, getSettings()); }
  if (p === '/api/settings/defaults' && m === 'GET') return json(res, 200, DEFAULT_SETTINGS);

  if (p === '/api/automations' && m === 'GET') return json(res, 200, listAutomations());
  if (p === '/api/automations' && m === 'POST') { const a = saveAutomation(body); logEvent('info', 'automation', `자동화 추가: #${a.id} ${a.name}`); return json(res, 200, a); }
  if (seg[0] === 'api' && seg[1] === 'automations' && seg[2]) {
    const id = Number(seg[2]);
    const cur = getAutomation(id);
    if (!cur) return json(res, 404, { error: 'not found' });
    if (m === 'GET' && !seg[3]) return json(res, 200, cur);
    if (m === 'PUT' && !seg[3]) { const a = saveAutomation({ ...cur, ...body }, id); logEvent('info', 'automation', `자동화 수정: #${id} ${a.name}`); return json(res, 200, a); }
    if (m === 'DELETE') { db.prepare('DELETE FROM automations WHERE id = ?').run(id); logEvent('info', 'automation', `자동화 삭제: #${id}`); return json(res, 200, { ok: true }); }
    if (m === 'POST' && seg[3] === 'toggle') { db.prepare('UPDATE automations SET enabled = 1 - enabled, updated_at = ? WHERE id = ?').run(now(), id); return json(res, 200, getAutomation(id)); }
    if (m === 'GET' && seg[3] === 'preview') return json(res, 200, buildFirstMessage(cur));
  }

  if (p === '/api/media' && m === 'GET') {
    const account = getAccount();
    if (!account) return json(res, 200, []);
    const fresh = url.searchParams.get('refresh') === '1';
    const cached = db.prepare('SELECT * FROM media_cache ORDER BY timestamp DESC LIMIT 100').all();
    if (cached.length && !fresh && now() - Math.max(...cached.map((c) => c.fetched_at)) < 10 * 60000) return json(res, 200, cached);
    try {
      const media = await clientFor(account).getMedia(100);
      for (const mm of media) upsertMedia(mm);
      return json(res, 200, db.prepare('SELECT * FROM media_cache ORDER BY timestamp DESC LIMIT 100').all());
    } catch (e) { return json(res, 502, { error: e.message, cached }); }
  }

  if (p === '/api/leads' && m === 'GET') {
    const rows = db.prepare(`SELECT d.*, a.name AS automation_name FROM deliveries d LEFT JOIN automations a ON a.id = d.automation_id ORDER BY d.id DESC LIMIT 1000`).all();
    if (url.searchParams.get('format') === 'csv') {
      const head = ['id', 'username', 'name', 'igsid', 'automation', 'stage', 'is_follower', 'gate_attempts', 'source', 'created_at', 'delivered_at'];
      const lines = [head.join(',')].concat(rows.map((r) => [r.id, r.username, r.name, r.igsid, r.automation_name, r.stage, r.is_follower, r.gate_attempts, r.source, r.created_at ? new Date(r.created_at).toISOString() : '', r.delivered_at ? new Date(r.delivered_at).toISOString() : '']
        .map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')));
      res.writeHead(200, { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="leads.csv"' });
      return res.end('\ufeff' + lines.join('\n'));
    }
    return json(res, 200, rows);
  }
  if (p === '/api/events' && m === 'GET') {
    const limit = Math.min(500, Number(url.searchParams.get('limit') || 100));
    return json(res, 200, db.prepare('SELECT * FROM events ORDER BY id DESC LIMIT ?').all(limit));
  }
  if (p === '/api/replies-pool' && m === 'GET') return json(res, 200, loadReplyPool());
  if (p === '/api/replies-pool' && m === 'PUT') return json(res, 200, saveReplyPool(body.pool || body));

  if (p === '/api/account/subscribe' && m === 'POST') {
    const account = getAccount(); if (!account) return json(res, 400, { error: '연결된 계정이 없습니다' });
    try { const r = await clientFor(account).subscribeWebhooks(); db.prepare('UPDATE accounts SET webhook_subscribed = 1 WHERE id = ?').run(account.id); return json(res, 200, r); } catch (e) { return json(res, 502, { error: e.message }); }
  }
  if (p === '/api/account/subscriptions' && m === 'GET') {
    const account = getAccount(); if (!account) return json(res, 400, { error: '연결된 계정이 없습니다' });
    try { return json(res, 200, await clientFor(account).getSubscribedApps()); } catch (e) { return json(res, 502, { error: e.message }); }
  }
  if (p === '/api/account/refresh-token' && m === 'POST') { const r = await refreshIfNeeded(true); return json(res, 200, { refreshed: !!r, account: publicAccount(getAccount()) }); }
  if (p === '/api/account/disconnect' && m === 'POST') { db.prepare('DELETE FROM accounts').run(); logEvent('info', 'disconnected', '계정 연결 해제'); return json(res, 200, { ok: true }); }
  if (p === '/api/account/me' && m === 'GET') {
    const account = getAccount(); if (!account) return json(res, 400, { error: '연결된 계정이 없습니다' });
    try {
      const me = await clientFor(account).getMe();
      db.prepare('UPDATE accounts SET username = ?, name = ?, profile_picture_url = ?, followers_count = ?, updated_at = ? WHERE id = ?').run(me.username || account.username, me.name || account.name, me.profile_picture_url || account.profile_picture_url, me.followers_count ?? account.followers_count, now(), account.id);
      return json(res, 200, me);
    } catch (e) { return json(res, 502, { error: e.message }); }
  }
  // ★ 팔로우 확인 도구: IGSID 로 즉시 조회
  if (p === '/api/tools/follow-check' && m === 'POST') {
    const account = getAccount(); if (!account) return json(res, 400, { error: '연결된 계정이 없습니다' });
    try { return json(res, 200, await clientFor(account).getUserProfile(String(body.igsid))); } catch (e) { return json(res, 502, { error: e.message }); }
  }
  if (p === '/api/tools/poll' && m === 'POST') { await pollOnce(); return json(res, 200, { ok: true }); }
  if (p === '/api/tools/tick' && m === 'POST') { await tick(); return json(res, 200, queueStatus()); }
  if (p === '/api/tools/flush' && m === 'POST') {
    // 큐에 대기 중인 작업을 지연 없이 즉시 실행 (테스트용)
    db.prepare("UPDATE dm_queue SET run_at = 0 WHERE status = 'pending'").run();
    db.prepare("UPDATE comment_reply_queue SET run_at = 0 WHERE status = 'pending'").run();
    for (let i = 0; i < 50; i++) { const before = pendingCount(); if (!before) break; await tick(true); if (pendingCount() === before) break; }
    return json(res, 200, queueStatus());
  }

  // ── 목(mock) 제어 (MOCK_INSTAGRAM=1 일 때만) ────────────────────────────
  if (config.mock && seg[1] === 'mock') {
    if (p === '/api/mock/calls' && m === 'GET') return json(res, 200, mockState.calls);
    if (p === '/api/mock/calls' && m === 'DELETE') { mockState.calls.length = 0; return json(res, 200, { ok: true }); }
    if (p === '/api/mock/follow' && m === 'POST') { mockState.follow[String(body.igsid)] = !!body.follows; return json(res, 200, mockState.follow); }
    if (p === '/api/mock/state' && m === 'POST') { Object.assign(mockState, body); return json(res, 200, { failTemplatePrivateReply: mockState.failTemplatePrivateReply, failCommentReply: mockState.failCommentReply }); }
    if (p === '/api/mock/connect' && m === 'POST') {
      const me = await clientFor({ access_token: 'mock' }).getMe();
      db.prepare('DELETE FROM accounts').run();
      db.prepare('INSERT INTO accounts(ig_user_id, app_scoped_id, username, name, followers_count, access_token, token_expires_at, webhook_subscribed, connected_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)')
        .run(String(me.user_id), String(me.id), me.username, me.name, me.followers_count, 'mock-token', now() + 60 * 86400000, 1, now(), now());
      return json(res, 200, publicAccount(getAccount()));
    }
  }
  return json(res, 404, { error: `no route: ${m} ${p}` });
}

// ── 메인 핸들러 ───────────────────────────────────────────────────────────
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const p = url.pathname;
  try {
    // 1) 웹훅
    if (p === '/webhook' && req.method === 'GET') {
      const ch = verifyChallenge(url.searchParams);
      if (ch) { logEvent('info', 'webhook', '웹훅 검증 요청 성공'); return text(res, 200, ch); }
      return text(res, 403, 'verify token mismatch');
    }
    if (p === '/webhook' && req.method === 'POST') {
      const raw = await readBody(req);
      if (!validSignature(raw, req.headers['x-hub-signature-256'])) { logEvent('warn', 'webhook', '서명 불일치 알림 거부'); return text(res, 401, 'invalid signature'); }
      let body; try { body = JSON.parse(raw.toString('utf8')); } catch { return text(res, 400, 'bad json'); }
      if (!eventKey(body)) return json(res, 200, { duplicate: true });
      // 처리 후 응답(최대 15초). 늦어지면 먼저 200 을 보내고 백그라운드로 계속
      const work = dispatch(body);
      const timeout = new Promise((r) => setTimeout(() => r({ timeout: true }), 15000));
      const result = await Promise.race([work, timeout]);
      work.catch((e) => logEvent('error', 'webhook', `dispatch 오류: ${e.message}`));
      return json(res, 200, result);
    }
    // 2) OAuth 연결
    if (p === '/auth/instagram') {
      if (!authorized(req)) { res.writeHead(401, { 'WWW-Authenticate': 'Basic realm="autodm"' }); return res.end('auth required'); }
      const state = crypto.randomBytes(12).toString('hex');
      oauthStates.set(state, now());
      return redirect(res, authorizeUrl(state));
    }
    if (p === '/auth/instagram/callback') {
      const err = url.searchParams.get('error');
      if (err) return text(res, 400, `연결 실패: ${err} - ${url.searchParams.get('error_description') || ''}`);
      const state = url.searchParams.get('state');
      if (!state || !oauthStates.has(state) || now() - oauthStates.get(state) > 10 * 60000) return text(res, 400, 'state 불일치 (다시 시도해 주세요)');
      oauthStates.delete(state);
      try { await connectAccount(url.searchParams.get('code')); return redirect(res, '/#connect'); } catch (e) { logEvent('error', 'oauth', `토큰 교환 실패: ${e.message}`, e.body); return text(res, 500, `토큰 교환 실패: ${e.message}`); }
    }
    // 2-b) Meta 버스니스 로그인 설정에 필수로 입력해야 하는 콜백 2개 (사용자가 연결을 해제/데이터 삭제 요청할 때 Meta가 호출)
    if (p === '/auth/instagram/deauthorize' && req.method === 'POST') {
      const raw = (await readBody(req)).toString('utf8');
      const sr = parseSignedRequest(raw);
      logEvent('info', 'deauthorize', `사용자가 앱 연결을 해제함 (user_id: ${sr?.user_id || 'unknown'})`);
      return json(res, 200, { ok: true });
    }
    if (p === '/auth/instagram/data-deletion' && req.method === 'POST') {
      const raw = (await readBody(req)).toString('utf8');
      const sr = parseSignedRequest(raw);
      const code = crypto.randomBytes(8).toString('hex');
      if (sr?.user_id) {
        const n = db.prepare('DELETE FROM deliveries WHERE igsid = ?').run(String(sr.user_id)).changes;
        logEvent('info', 'data_deletion', `데이터 삭제 요청 처리 (user_id: ${sr.user_id}, 삭제 ${n}건, 코드 ${code})`);
      }
      return json(res, 200, { url: `${config.publicUrl}/deletion-status?code=${code}`, confirmation_code: code });
    }
    if (p === '/deletion-status') return text(res, 200, `데이터 삭제 요청이 처리되었습니다. 확인 코드: ${url.searchParams.get('code') || ''}`);
    if (p === '/privacy') return text(res, 200, PRIVACY_TEXT);
    if (p === '/healthz') return json(res, 200, { ok: true, account: !!getAccount(), mock: config.mock });
    // 3) 대시보드 & API (인증)
    if (!authorized(req)) { res.writeHead(401, { 'WWW-Authenticate': 'Basic realm="autodm"' }); return res.end('auth required'); }
    if (p.startsWith('/api/')) return await api(req, res, url);
    // 4) 정적 파일
    let file = p === '/' ? '/index.html' : p;
    file = path.normalize(file).replace(/^(\.\.[/\\])+/, '');
    const abs = path.join(PUBLIC_DIR, file);
    if (abs.startsWith(PUBLIC_DIR) && fs.existsSync(abs) && fs.statSync(abs).isFile()) {
      res.writeHead(200, { 'Content-Type': MIME[path.extname(abs)] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
      return fs.createReadStream(abs).pipe(res);
    }
    return text(res, 404, 'not found');
  } catch (e) {
    logEvent('error', 'server', `${req.method} ${p}: ${e.message}`);
    if (!res.headersSent) json(res, 500, { error: e.message });
  }
});

server.listen(config.port, () => {
  console.log(`\n▶ Instagram AutoDM 서버 시작: http://localhost:${config.port}`);
  console.log(`  공개 URL     : ${config.publicUrl}`);
  console.log(`  웹훅 URL     : ${webhookUrl()}`);
  console.log(`  OAuth 리다이렉트: ${redirectUri()}`);
  console.log(`  모드         : ${config.mock ? 'MOCK (Instagram API 호출 안 함)' : 'LIVE'}${config.commentPolling ? ' + 댓글 폴링' : ''}\n`);
  startQueues();
  startPoller();
  startTokenRefresher();
});
