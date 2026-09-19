// 자동화 핵심 로직
//  1) 댓글 → 키워드 매칭 → 대댓글 예약 + 버튼형 Private Reply 발송
//  2) 버튼 클릭(postback) → ★ 팔로우 확인 → 팔로워면 리드마그넷 전송 / 아니면 "팔로우했어요" 재시도 버튼
//  3) DM 키워드 → 같은 흐름
import {
  db, now, logEvent, bumpStat, getAccount, getSetting, settingOn, listAutomations, getAutomation,
  findDelivery, createDelivery, updateDelivery, markProcessed,
} from './db.js';
import { clientFor, msg, InstagramApiError } from './instagram.js';
import { matchKeyword, render, loadReplyPool, pickReply, aiVariation } from './text.js';
import { enqueueDm, enqueueCommentReply, recentReplyTexts } from './queues.js';

const PAYLOAD_LM = 'LM';        // 리드마그넷 버튼
const PAYLOAD_RECHECK = 'RC';   // 팔로우 재확인 버튼

// ── 게시물 정보 캐시 ('다음 발행 게시물에 적용' 판정용) ──────────────────────
async function mediaTimestamp(ig, mediaId) {
  const row = db.prepare('SELECT timestamp FROM media_cache WHERE id = ?').get(mediaId);
  if (row?.timestamp) return row.timestamp;
  try {
    const m = await ig.get(String(mediaId), { fields: 'id,caption,media_type,media_product_type,thumbnail_url,permalink,timestamp' });
    upsertMedia(m);
    return m.timestamp || null;
  } catch { return null; }
}
export function upsertMedia(m) {
  db.prepare(`INSERT INTO media_cache(id, caption, media_type, media_product_type, thumbnail_url, permalink, timestamp, fetched_at) VALUES(?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET caption = excluded.caption, media_type = excluded.media_type, media_product_type = excluded.media_product_type,
    thumbnail_url = excluded.thumbnail_url, permalink = excluded.permalink, timestamp = excluded.timestamp, fetched_at = excluded.fetched_at`)
    .run(String(m.id), m.caption || '', m.media_type || '', m.media_product_type || '', m.thumbnail_url || m.media_url || '', m.permalink || '', m.timestamp || '', now());
}

async function automationAppliesToMedia(ig, a, mediaId) {
  if (a.post_scope === 'all') return true;
  if ((a.media_ids || []).map(String).includes(String(mediaId))) return true;
  if (a.apply_to_future) {
    const ts = await mediaTimestamp(ig, mediaId);
    if (ts && new Date(ts).getTime() >= (a.created_at || 0)) return true;
  }
  return false;
}

// 여러 자동화가 매칭되면: 특정 게시물 > 전체, 특정 키워드 > 불특정
function rankAutomation(a) {
  return (a.post_scope === 'selected' ? 2 : 0) + (a.keyword_mode !== 'any' ? 1 : 0);
}

// ── 첫 DM 메시지 구성 ────────────────────────────────────────────────────
export function buildFirstMessage(a) {
  const buttons = (a.buttons || []).slice(0, 3);
  const needsGate = !!a.follow_gate;
  const mkButtons = () => buttons.map((b, i) => {
    // 링크만 있는 버튼은 즉시 이동(게이트 불가). 답장 내용이 있으면 postback → 팔로우 확인 후 공개
    if (b.url && !b.reply) return msg.webUrl(b.label, b.url);
    return msg.postback(b.label, `${PAYLOAD_LM}:${a.id}:${i}`);
  });

  if (a.dm_type === 'text' && !needsGate) {
    return { message: msg.text(a.dm_text || a.title || ''), gated: false };
  }
  if (a.dm_type === 'text' && needsGate) {
    // 텍스트형이지만 팔로우 확인이 필요하면 버튼 하나를 붙여 postback 을 유도
    const label = buttons[0]?.label || '자료 받기';
    return { message: msg.button(a.dm_text || a.title || '아래 버튼을 눌러 자료를 받아가세요!', [msg.postback(label, `${PAYLOAD_LM}:${a.id}:0`)]), gated: true };
  }
  // 버튼형: 이미지/제목/부제목 + 버튼
  if (a.image_url || a.subtitle) {
    return { message: msg.generic({ title: a.title || a.name, subtitle: a.subtitle, image_url: a.image_url, buttons: mkButtons() }), gated: needsGate };
  }
  return { message: msg.button(a.title || a.dm_text || a.name, mkButtons()), gated: needsGate };
}

function buttonReplyText(a, idx) {
  const b = (a.buttons || [])[idx];
  if (b?.reply) return b.reply + (b.url && !b.reply.includes(b.url) ? `\n${b.url}` : '');
  if (b?.url) return b.url;
  return a.dm_text || a.title || '';
}

// ── 1) 댓글 처리 ─────────────────────────────────────────────────────────
export async function handleComment({ account, comment, source = 'comment' }) {
  account = account || getAccount();
  if (!account || !settingOn('master_switch')) return { skipped: 'off' };
  const from = comment.from || {};
  const igsid = String(from.id || '');
  const username = from.username || '';
  const text = comment.text || '';
  const mediaId = String(comment.media?.id || comment.media_id || '');
  const commentId = String(comment.id || '');
  if (!commentId) return { skipped: 'no_id' };

  // 내 댓글(자동 대댓글 포함)은 무시 → 무한 루프 방지
  if (igsid && (igsid === String(account.ig_user_id) || igsid === String(account.app_scoped_id))) return { skipped: 'self' };
  if (username && account.username && username.toLowerCase() === String(account.username).toLowerCase()) return { skipped: 'self' };

  // 중복 알림 방지
  try {
    db.prepare('INSERT INTO comments_seen(comment_id, media_id, igsid, username, text, received_at) VALUES(?,?,?,?,?,?)')
      .run(commentId, mediaId, igsid, username, text, now());
  } catch { return { skipped: 'duplicate' }; }
  bumpStat('comments');

  const ig = clientFor(account);
  const fuzzy = settingOn('keyword_fuzzy');
  const candidates = [];
  for (const a of listAutomations()) {
    if (!a.enabled || a.trigger_type !== 'comment') continue;
    if (!(await automationAppliesToMedia(ig, a, mediaId))) continue;
    const m = matchKeyword(text, a, fuzzy);
    if (m.matched) candidates.push({ a, keyword: m.keyword });
  }
  if (!candidates.length) {
    logEvent('info', 'comment_nomatch', `매칭 없음: @${username} "${text.slice(0, 40)}"`, { comment_id: commentId, media_id: mediaId });
    return { skipped: 'nomatch' };
  }
  candidates.sort((x, y) => rankAutomation(y.a) - rankAutomation(x.a));
  const { a, keyword } = candidates[0];
  db.prepare('UPDATE comments_seen SET automation_id = ?, matched = 1 WHERE comment_id = ?').run(a.id, commentId);

  // 같은 사람이 같은 자동화에 24시간 내 중복 댓글 → 대댓글만 하고 DM 은 생략 (스팸 방지)
  const prev = findDelivery(a.id, igsid);
  const dup = prev && now() - prev.created_at < 86400000 && prev.stage !== 'failed';

  // 대댓글 예약
  let replyText = null;
  if (a.comment_reply_mode !== 'off' && settingOn('comment_reply_enabled')) {
    const pool = a.comment_reply_mode === 'custom' && a.comment_replies?.length ? a.comment_replies : loadReplyPool();
    const picked = pickReply(pool, recentReplyTexts(20));
    if (picked) {
      replyText = render(picked, { username, name: from.name });
      enqueueCommentReply({ comment_id: commentId, media_id: mediaId, igsid, username, automation_id: a.id, text: replyText });
    }
  }
  if (dup) {
    logEvent('info', 'comment_dup', `@${username} 24시간 내 중복 댓글 → DM 생략 (자동화 #${a.id})`, { comment_id: commentId });
    return { automation: a.id, duplicate: true };
  }

  // 첫 DM (Private Reply) 예약
  const { message, gated } = buildFirstMessage(a);
  const deliveryId = createDelivery({ automation_id: a.id, igsid, username, name: from.name, source, comment_id: commentId, media_id: mediaId, stage: 'queued' });
  const fallback = msg.text(render(getSetting('fallback_prompt_message'), { username, name: from.name }));
  const finalText = !gated && !message.attachment; // 게이트 없는 텍스트 DM 은 이 메시지 자체가 리드마그넷
  if (finalText) message.text = render(message.text, { username, name: from.name });
  enqueueDm({ delivery_id: deliveryId, kind: 'private_reply', igsid, comment_id: commentId, payload: message, fallback_payload: message.attachment ? fallback : null, final: finalText });
  logEvent('info', 'comment_matched', `댓글 매칭: @${username} "${text.slice(0, 40)}" → 자동화 #${a.id} "${a.name}"${keyword ? ` (키워드: ${keyword})` : ''}${gated ? ' [팔로우 게이트]' : ''}`,
    { comment_id: commentId, media_id: mediaId, delivery_id: deliveryId });
  return { automation: a.id, delivery_id: deliveryId, gated, replyText };
}

// ── 2) 버튼 클릭 → 팔로우 확인 → 전달 ─────────────────────────────────────
export async function handlePostback({ account, igsid, payload, mid, title }) {
  account = account || getAccount();
  if (!account || !settingOn('master_switch')) return { skipped: 'off' };
  if (mid && !markProcessed(`pb:${mid}`)) return { skipped: 'duplicate' };
  const [kind, aidStr, idxStr] = String(payload || '').split(':');
  if (![PAYLOAD_LM, PAYLOAD_RECHECK].includes(kind)) {
    logEvent('info', 'postback_unknown', `알 수 없는 postback: ${payload}`, { igsid, title });
    return { skipped: 'unknown' };
  }
  const a = getAutomation(Number(aidStr));
  const idx = Number(idxStr) || 0;
  if (!a) { logEvent('warn', 'postback_missing', `삭제된 자동화 #${aidStr} 버튼 클릭`, { igsid }); return { skipped: 'missing' }; }
  return deliverLeadMagnet({ account, a, igsid, idx, recheck: kind === PAYLOAD_RECHECK, source: 'postback' });
}

// ★ 팔로우 게이트: 팔로워에게만 리드마그넷 공개
export async function deliverLeadMagnet({ account, a, igsid, idx = 0, recheck = false, source = 'postback', userHint = {} }) {
  const ig = clientFor(account);
  let delivery = findDelivery(a.id, igsid);
  if (!delivery) {
    const id = createDelivery({ automation_id: a.id, igsid, username: userHint.username, name: userHint.name, source: 'dm', stage: 'dm_sent' });
    delivery = db.prepare('SELECT * FROM deliveries WHERE id = ?').get(id);
  }
  const wasBlocked = delivery.stage === 'gate_blocked';

  // 프로필 조회 (이름 치환 + 팔로우 여부)
  let profile = null, profileError = null;
  try { profile = await ig.getUserProfile(igsid); } catch (e) { profileError = e; }
  const user = { username: profile?.username || delivery.username || userHint.username, name: profile?.name || delivery.name || userHint.name };
  if (profile) updateDelivery(delivery.id, { username: user.username || null, name: user.name || null, follower_count: profile.follower_count ?? null });

  if (a.follow_gate) {
    bumpStat('gate_checks');
    let isFollower;
    if (profile) isFollower = !!profile.is_user_follow_business;
    else {
      const failOpen = settingOn('gate_fail_open');
      logEvent(failOpen ? 'warn' : 'error', 'gate_check_error', `팔로우 확인 API 실패 (${failOpen ? '통과 처리' : '차단 처리'}): ${profileError?.message}`, { igsid, automation: a.id });
      isFollower = failOpen;
    }
    if (!isFollower) {
      const attempts = (delivery.gate_attempts || 0) + 1;
      updateDelivery(delivery.id, { stage: 'gate_blocked', gate_attempts: attempts, is_follower: 0, button_index: idx });
      bumpStat('gate_blocked');
      const text = render(attempts > 1 ? getSetting('follow_still_not_message') : getSetting('non_follower_message'), user);
      const label = getSetting('follow_retry_button_label') || '팔로우했어요.';
      try {
        await ig.sendMessage(igsid, msg.button(text, [msg.postback(label, `${PAYLOAD_RECHECK}:${a.id}:${idx}`)]));
      } catch (e) { logEvent('error', 'gate_message_error', `비팔로워 안내 발송 실패: ${e.message}`, { igsid }); }
      logEvent('info', 'gate_blocked', `팔로우 미확인 → 안내 발송 (@${user.username || igsid}, ${attempts}회차, 자동화 #${a.id})`, { igsid, automation: a.id });
      return { blocked: true, attempts };
    }
    updateDelivery(delivery.id, { is_follower: 1 });
    if (wasBlocked || recheck) bumpStat('gate_converted');
  }

  // 팔로워 확인됨(또는 게이트 꺼짐) → 리드마그넷 전송
  let text = render(buttonReplyText(a, idx), user);
  if (a.ai_variation) text = await aiVariation(text);
  try {
    await ig.sendMessage(igsid, msg.text(text));
    const followup = getSetting('delivered_followup');
    if (followup) await ig.sendMessage(igsid, msg.text(render(followup, user)));
  } catch (e) {
    const info = e instanceof InstagramApiError ? `${e.message} (code ${e.code})` : e.message;
    updateDelivery(delivery.id, { stage: 'failed', last_error: info });
    logEvent('error', 'deliver_failed', `리드마그넷 전송 실패: ${info}`, { igsid, automation: a.id });
    return { failed: true, error: info };
  }
  updateDelivery(delivery.id, { stage: 'delivered', delivered_at: now(), button_index: idx, last_error: null });
  db.prepare('UPDATE automations SET delivered_count = delivered_count + 1 WHERE id = ?').run(a.id);
  bumpStat('delivered');
  logEvent('info', 'delivered', `리드마그넷 전송 완료 → @${user.username || igsid} (자동화 #${a.id} "${a.name}"${wasBlocked || recheck ? ', 팔로우 후 전환' : ''})`, { igsid, automation: a.id, delivery_id: delivery.id });
  return { delivered: true, converted: wasBlocked || recheck };
}

// ── 3) DM 수신 처리 (DM→DM 자동화 + 폴백 답장) ─────────────────────────────
export async function handleMessage({ account, igsid, text, mid, quickReplyPayload }) {
  account = account || getAccount();
  if (!account || !settingOn('master_switch')) return { skipped: 'off' };
  if (mid && !markProcessed(`msg:${mid}`)) return { skipped: 'duplicate' };
  if (quickReplyPayload) return handlePostback({ account, igsid, payload: quickReplyPayload, mid: null });
  text = String(text || '');

  // A. 템플릿 실패 폴백: "받기" 라고 답장한 사용자 → 게이트 확인 후 전달
  const waiting = db.prepare("SELECT * FROM deliveries WHERE igsid = ? AND stage = 'awaiting_reply' ORDER BY id DESC LIMIT 1").get(igsid);
  if (waiting) {
    const a = getAutomation(waiting.automation_id);
    // 사용자가 무엇이든 답장하면 24시간 창이 열리므로 바로 게이트 확인으로 진행 (키워드는 안내용)
    if (a && text.trim()) return deliverLeadMagnet({ account, a, igsid, idx: 0, source: 'dm_reply' });
  }

  // B. DM 키워드 자동화
  const fuzzy = settingOn('keyword_fuzzy');
  const hits = listAutomations().filter((a) => a.enabled && (a.trigger_type === 'dm' || a.also_dm) && matchKeyword(text, a, fuzzy).matched);
  if (!hits.length) return { skipped: 'nomatch' };
  hits.sort((x, y) => rankAutomation(y) - rankAutomation(x));
  const a = hits[0];
  const prev = findDelivery(a.id, igsid);
  if (prev && now() - prev.created_at < 86400000 && prev.stage === 'delivered') return { skipped: 'recent' };

  const { message, gated } = buildFirstMessage(a);
  if (!gated && message.text) {
    // 텍스트형 + 게이트 없음 → 바로 전달로 처리
    return deliverLeadMagnet({ account, a, igsid, idx: 0, source: 'dm' });
  }
  const deliveryId = createDelivery({ automation_id: a.id, igsid, source: 'dm', stage: 'queued' });
  enqueueDm({ delivery_id: deliveryId, kind: 'message', igsid, payload: message });
  logEvent('info', 'dm_matched', `DM 키워드 매칭: "${text.slice(0, 40)}" → 자동화 #${a.id}`, { igsid, delivery_id: deliveryId });
  return { automation: a.id, delivery_id: deliveryId, gated };
}
