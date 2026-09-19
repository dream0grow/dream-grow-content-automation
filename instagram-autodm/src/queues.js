// 발송 큐: 자동 DM(Private Reply/DM) 과 자동 대댓글을 제한 규칙에 맞춰 천천히 보냅니다.
//  - DM: 시간당 제한(dm_hour_limit) → 발송 간격 = 3600/limit 초
//  - 대댓글: 게시물별 시간당 제한 + 무작위 지연(delay_min~max) + 24시간 내 오류 N회면 자동 중단 (KittyChat 안전장치와 동일)
import { db, now, logEvent, bumpStat, getAccount, settingNum, settingOn, setSettings, updateDelivery, cleanupOld } from './db.js';
import { clientFor, InstagramApiError } from './instagram.js';

const TRANSIENT_CODES = new Set([1, 2, 4, 17, 32, 613]); // 일시 오류/호출 제한 → 재시도
let lastDmSentAt = 0;
let running = false;

export function enqueueDm({ delivery_id, kind, igsid, comment_id, payload, fallback_payload, delayMs = 0, final = false, tag = null }) {
  const r = db.prepare(`INSERT INTO dm_queue(delivery_id, kind, igsid, comment_id, payload, fallback_payload, final, tag, run_at, created_at)
    VALUES(?,?,?,?,?,?,?,?,?,?)`).run(delivery_id || null, kind, igsid || null, comment_id || null, JSON.stringify(payload), fallback_payload ? JSON.stringify(fallback_payload) : null, final ? 1 : 0, tag, now() + delayMs, now());
  return Number(r.lastInsertRowid);
}

export function enqueueCommentReply({ comment_id, media_id, igsid, username, automation_id, text }) {
  const min = Math.max(0, settingNum('comment_reply_delay_min'));
  const max = Math.max(min, settingNum('comment_reply_delay_max'));
  const delaySec = min + Math.random() * (max - min);
  const r = db.prepare(`INSERT INTO comment_reply_queue(comment_id, media_id, igsid, username, automation_id, text, run_at, created_at)
    VALUES(?,?,?,?,?,?,?,?)`).run(comment_id, media_id || null, igsid || null, username || null, automation_id, text, now() + Math.round(delaySec * 1000), now());
  return Number(r.lastInsertRowid);
}

function errInfo(e) {
  if (e instanceof InstagramApiError) return `${e.message} (code ${e.code}${e.subcode ? '/' + e.subcode : ''})`;
  return e?.message || String(e);
}

// ── DM 큐 ───────────────────────────────────────────────────────────────
async function processDmQueue(force = false) {
  const account = getAccount();
  if (!account) return;
  const limit = Math.max(1, settingNum('dm_hour_limit'));
  const spacingMs = Math.round(3600000 / limit);
  if (!force && now() - lastDmSentAt < spacingMs) return;

  const job = db.prepare("SELECT * FROM dm_queue WHERE status = 'pending' AND run_at <= ? ORDER BY run_at ASC LIMIT 1").get(now());
  if (!job) return;
  const ig = clientFor(account);
  const payload = JSON.parse(job.payload);
  const fallback = job.fallback_payload ? JSON.parse(job.fallback_payload) : null;
  db.prepare('UPDATE dm_queue SET attempts = attempts + 1 WHERE id = ?').run(job.id);

  try {
    let res;
    if (job.kind === 'private_reply') {
      try {
        res = await ig.sendPrivateReply(job.comment_id, payload);
      } catch (e) {
        // 템플릿(버튼) Private Reply 가 거부되면 텍스트 폴백 → 사용자가 답장하면 이어서 진행
        if (fallback && payload.attachment && e instanceof InstagramApiError && e.status && e.status < 500 && !TRANSIENT_CODES.has(e.code)) {
          logEvent('warn', 'dm_fallback', `버튼형 Private Reply 실패 → 텍스트 폴백 전송: ${errInfo(e)}`, { comment_id: job.comment_id });
          res = await ig.sendPrivateReply(job.comment_id, fallback);
          if (job.delivery_id) {
            const d = db.prepare('SELECT igsid FROM deliveries WHERE id = ?').get(job.delivery_id);
            updateDelivery(job.delivery_id, { stage: 'awaiting_reply', ...(d && !d.igsid && res?.recipient_id ? { igsid: String(res.recipient_id) } : {}) });
          }
          finishDm(job, res);
          return;
        }
        throw e;
      }
    } else {
      res = await ig.sendMessage(job.igsid, payload);
    }
    if (job.delivery_id) {
      const d = db.prepare('SELECT stage, igsid, automation_id FROM deliveries WHERE id = ?').get(job.delivery_id);
      const patch = {};
      if (d && (d.stage === 'queued' || !d.stage)) patch.stage = 'dm_sent';
      if (d && !d.igsid && res?.recipient_id) patch.igsid = String(res.recipient_id);
      if (job.final) {
        // 게이트 없는 텍스트 DM: 이 메시지가 곱 리드마그넷 → 전달 완료
        patch.stage = 'delivered'; patch.delivered_at = now();
        if (d?.automation_id) db.prepare('UPDATE automations SET delivered_count = delivered_count + 1 WHERE id = ?').run(d.automation_id);
        bumpStat('delivered');
      }
      updateDelivery(job.delivery_id, patch);
    }
    finishDm(job, res);
  } catch (e) {
    const info = errInfo(e);
    const transient = e instanceof InstagramApiError && (e.status >= 500 || TRANSIENT_CODES.has(e.code));
    if (transient && job.attempts < 3) {
      db.prepare("UPDATE dm_queue SET run_at = ?, error = ? WHERE id = ?").run(now() + 60000 * (job.attempts + 1), info, job.id);
      logEvent('warn', 'dm_retry', `DM 일시 오류, 재시도 예정: ${info}`, { job: job.id });
    } else {
      db.prepare("UPDATE dm_queue SET status = 'failed', error = ?, done_at = ? WHERE id = ?").run(info, now(), job.id);
      if (job.delivery_id) updateDelivery(job.delivery_id, { stage: 'failed', last_error: info });
      logEvent('error', 'dm_failed', `자동 DM 발송 실패: ${info}`, { job: job.id, comment_id: job.comment_id, igsid: job.igsid });
    }
  }
}
function finishDm(job, res) {
  lastDmSentAt = now();
  db.prepare("UPDATE dm_queue SET status = 'done', done_at = ? WHERE id = ?").run(now(), job.id);
  bumpStat('dm_sent');
  if (job.delivery_id) {
    const d = db.prepare('SELECT automation_id FROM deliveries WHERE id = ?').get(job.delivery_id);
    if (d?.automation_id) db.prepare('UPDATE automations SET send_count = send_count + 1 WHERE id = ?').run(d.automation_id);
  }
  logEvent('info', 'dm_sent', `자동 DM 발송 완료 (${job.kind})`, { job: job.id, message_id: res?.message_id, recipient_id: res?.recipient_id });
}

// ── 대댓글 큐 ────────────────────────────────────────────────────────────
function recentCommentErrors24h() {
  return db.prepare("SELECT COUNT(*) AS c FROM events WHERE type = 'comment_reply_error' AND created_at > ?").get(now() - 86400000).c;
}
export function recentReplyTexts(n = 20) {
  return db.prepare("SELECT text FROM comment_reply_queue WHERE status = 'done' ORDER BY done_at DESC LIMIT ?").all(n).map((r) => r.text);
}

async function processCommentReplyQueue() {
  if (!settingOn('comment_reply_enabled')) return;
  const account = getAccount();
  if (!account) return;
  const job = db.prepare("SELECT * FROM comment_reply_queue WHERE status = 'pending' AND run_at <= ? ORDER BY run_at ASC LIMIT 1").get(now());
  if (!job) return;

  // 너무 오래된 작업은 버림 (6시간)
  if (now() - job.created_at > 6 * 3600000) {
    db.prepare("UPDATE comment_reply_queue SET status = 'dropped', done_at = ? WHERE id = ?").run(now(), job.id);
    return;
  }
  // 게시물별 시간당 제한
  const perPost = Math.max(1, settingNum('comment_reply_post_hour_limit'));
  const doneLastHour = db.prepare("SELECT COUNT(*) AS c FROM comment_reply_queue WHERE status = 'done' AND media_id IS ? AND done_at > ?").get(job.media_id, now() - 3600000).c;
  if (doneLastHour >= perPost) {
    db.prepare('UPDATE comment_reply_queue SET run_at = ? WHERE id = ?').run(now() + 10 * 60000, job.id); // 10분 뒤 재시도
    return;
  }
  const ig = clientFor(account);
  db.prepare('UPDATE comment_reply_queue SET attempts = attempts + 1 WHERE id = ?').run(job.id);
  try {
    const res = await ig.replyToComment(job.comment_id, job.text);
    db.prepare("UPDATE comment_reply_queue SET status = 'done', done_at = ? WHERE id = ?").run(now(), job.id);
    bumpStat('comment_replies');
    logEvent('info', 'comment_reply', `자동 대댓글 게시: "${job.text.slice(0, 60)}"`, { comment_id: job.comment_id, reply_id: res?.id });
  } catch (e) {
    const info = errInfo(e);
    db.prepare("UPDATE comment_reply_queue SET status = 'failed', error = ?, done_at = ? WHERE id = ?").run(info, now(), job.id);
    logEvent('error', 'comment_reply_error', `자동 대댓글 실패: ${info}`, { comment_id: job.comment_id });
    // 경고 감지 — KittyChat 과 동일한 단계적 대응
    //   1·2차: 이벤트 경고 + 대댓글 간격 자동 증가 (활동 속도를 낮춤)
    //   3차  : 대댓글 시스템 중단 (자동 DM 은 계속 작동)
    const errs = recentCommentErrors24h();
    const threshold = Math.max(1, settingNum('warning_threshold'));
    if (settingOn('auto_disable_on_warnings') && errs >= threshold) {
      setSettings({ comment_reply_enabled: '0' });
      logEvent('warn', 'comment_reply_disabled',
        `인스타그램 대댓글 오류가 24시간 내 ${errs}회 발생해 자동 대댓글을 일시 중단했습니다. 5~7일간 꺼두었다가 지연 시간을 5분(300초) 이상으로 늘리고 다시 켜주세요. 자동 DM 은 계속 작동합니다.`);
    } else if (errs >= 1) {
      let extra = '';
      if (settingOn('warning_backoff_enabled')) {
        const step = Math.max(0, settingNum('warning_backoff_step'));
        const cap = Math.max(60, settingNum('warning_backoff_max'));
        const min = Math.min(cap, Math.max(0, settingNum('comment_reply_delay_min')) + step);
        const max = Math.min(cap + 120, Math.max(min, settingNum('comment_reply_delay_max') + step));
        setSettings({ comment_reply_delay_min: String(Math.round(min)), comment_reply_delay_max: String(Math.round(max)) });
        extra = ` 대댓글 간격을 ${Math.round(min)}~${Math.round(max)}초로 자동 증가했습니다.`;
      }
      logEvent('warn', 'comment_reply_warning',
        `경고 감지: 자동 대댓글 오류 ${errs}/${threshold}.${extra} ${threshold}회 도달 시 자동 대댓글이 중단됩니다.`);
    }
  }
}

export function startQueues() {
  if (running) return;
  running = true;
  setInterval(() => processDmQueue().catch((e) => logEvent('error', 'queue', `DM 큐 오류: ${e.message}`)), 1000);
  setInterval(() => processCommentReplyQueue().catch((e) => logEvent('error', 'queue', `대댓글 큐 오류: ${e.message}`)), 5000);
  setInterval(() => { try { cleanupOld(); } catch {} }, 6 * 3600000);
}

// 테스트/관리용: 큐를 즉시 한 번 돌림 (force=true 면 DM 발송 간격 무시)
export async function tick(force = false) {
  await processDmQueue(force);
  await processCommentReplyQueue();
}
export function pendingCount() {
  return db.prepare("SELECT (SELECT COUNT(*) FROM dm_queue WHERE status = 'pending' AND run_at <= ?) + (SELECT COUNT(*) FROM comment_reply_queue WHERE status = 'pending' AND run_at <= ?) AS c").get(now(), now()).c;
}
export function queueStatus() {
  return {
    dm_pending: db.prepare("SELECT COUNT(*) AS c FROM dm_queue WHERE status = 'pending'").get().c,
    comment_pending: db.prepare("SELECT COUNT(*) AS c FROM comment_reply_queue WHERE status = 'pending'").get().c,
    comment_errors_24h: recentCommentErrors24h(),
    scheduled_pending: db.prepare("SELECT COUNT(*) AS c FROM dm_queue WHERE status = 'pending' AND run_at > ?").get(now()).c,
    next_scheduled_at: db.prepare("SELECT MIN(run_at) AS t FROM dm_queue WHERE status = 'pending' AND run_at > ?").get(now()).t || null,
  };
}
