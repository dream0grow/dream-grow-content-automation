// Meta 웹훅 수신: 검증(GET) · 서명 확인 · 이벤트 파싱/분배
import crypto from 'node:crypto';
import { config } from './config.js';
import { getAccount, logEvent, markProcessed } from './db.js';
import { handleComment, handlePostback, handleMessage } from './automation.js';

export function verifyChallenge(query) {
  if (query.get('hub.mode') === 'subscribe' && query.get('hub.verify_token') === config.verifyToken) return query.get('hub.challenge');
  return null;
}

// Meta 앱에는 시크릿이 2개(Meta 앱 시크릿 / Instagram 앱 시크릿) 있고, Instagram 웹훅은 Instagram 앱 시크릿으로 서명된다는
// 실측 보고가 있습니다. 혼란을 피하기 위해 설정된 시크릿 중 하나라도 맞으면 통과시킵니다.
let signatureHintLogged = false;
export function validSignature(rawBody, header) {
  const secrets = [config.appSecret, config.metaAppSecret].filter(Boolean);
  if (!secrets.length) return true; // 개발 편의: 시크릿이 없으면 검증 생략
  if (!header || !header.startsWith('sha256=')) return false;
  const given = Buffer.from(header.slice(7), 'hex');
  for (const s of secrets) {
    const expected = crypto.createHmac('sha256', s).update(rawBody).digest();
    if (given.length === expected.length && crypto.timingSafeEqual(given, expected)) return true;
  }
  if (!signatureHintLogged) {
    signatureHintLogged = true;
    logEvent('error', 'webhook_signature', 'Meta 웹훅 서명이 설정된 시크릿과 맞지 않습니다. IG_APP_SECRET(Instagram 앱 시크릿, Business login settings)과 META_APP_SECRET(앱 설정 > 기본 설정)을 모두 .env 에 넣어 주세요.');
  }
  return false;
}

// 알림 본문 → 처리 가능한 이벤트 목록
export function parseEvents(body) {
  const events = [];
  if (!body || body.object !== 'instagram' || !Array.isArray(body.entry)) return events;
  for (const entry of body.entry) {
    const igId = String(entry.id || '');
    // comments (changes[] 형태 또는 field/value 평면 형태 모두 지원)
    const changes = Array.isArray(entry.changes) ? entry.changes : (entry.field ? [{ field: entry.field, value: entry.value }] : []);
    for (const ch of changes) {
      if (ch.field === 'comments' || ch.field === 'live_comments') events.push({ type: 'comment', igId, comment: ch.value, live: ch.field === 'live_comments' });
    }
    for (const m of entry.messaging || []) {
      const sender = String(m.sender?.id || '');
      if (m.postback) events.push({ type: 'postback', igId, igsid: sender, payload: m.postback.payload, title: m.postback.title, mid: m.postback.mid, timestamp: m.timestamp });
      else if (m.message) {
        if (m.message.is_echo || sender === igId) continue; // 내가 보낸 메시지
        events.push({ type: 'message', igId, igsid: sender, text: m.message.text || '', mid: m.message.mid, quickReplyPayload: m.message.quick_reply?.payload, attachments: m.message.attachments || [], timestamp: m.timestamp });
      }
      // read/reaction/referral 등은 무시
    }
  }
  return events;
}

export async function dispatch(body) {
  const events = parseEvents(body);
  const account = getAccount();
  const results = [];
  for (const ev of events) {
    try {
      if (account && ev.igId && String(account.ig_user_id) !== ev.igId && String(account.app_scoped_id || '') !== ev.igId) {
        logEvent('warn', 'webhook_other_account', `연결되지 않은 계정(${ev.igId})의 이벤트 수신 → 무시`);
        continue;
      }
      if (ev.type === 'comment') {
        if (ev.live) continue; // 라이브 댓글은 미지원
        results.push(await handleComment({ account, comment: ev.comment, source: 'comment' }));
      } else if (ev.type === 'postback') {
        results.push(await handlePostback({ account, igsid: ev.igsid, payload: ev.payload, mid: ev.mid, title: ev.title }));
      } else if (ev.type === 'message') {
        results.push(await handleMessage({ account, igsid: ev.igsid, text: ev.text, mid: ev.mid, quickReplyPayload: ev.quickReplyPayload, attachments: ev.attachments }));
      }
    } catch (e) {
      logEvent('error', 'webhook_handler', `이벤트 처리 오류(${ev.type}): ${e.message}`, { stack: e.stack?.split('\n').slice(0, 3) });
      results.push({ error: e.message });
    }
  }
  return { events: events.length, results };
}

// 동일 알림 재전송 방지 키
export function eventKey(body) {
  const h = crypto.createHash('sha1').update(JSON.stringify(body)).digest('hex');
  return markProcessed(`wh:${h}`);
}
