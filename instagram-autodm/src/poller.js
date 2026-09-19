// 폴백: 웹훅이 오지 않는 환경(앱 검수 전 등)에서 댓글을 주기적으로 조회해 같은 흐름으로 처리
import { config } from './config.js';
import { db, getAccount, logEvent, listAutomations, now } from './db.js';
import { clientFor } from './instagram.js';
import { handleComment, upsertMedia } from './automation.js';

let timer = null;
let lastRun = 0;

async function pollOnce() {
  const account = getAccount();
  if (!account) return;
  const ig = clientFor(account);
  const autos = listAutomations().filter((a) => a.enabled && a.trigger_type === 'comment');
  if (!autos.length) return;

  // 대상 게시물: 선택된 게시물 + (전체/미래 적용이 있으면) 최근 게시물 10개
  const targets = new Set();
  let needRecent = false;
  for (const a of autos) {
    if (a.post_scope === 'all' || a.apply_to_future) needRecent = true;
    for (const id of a.media_ids || []) targets.add(String(id));
  }
  if (needRecent) {
    const media = await ig.getMedia(10);
    for (const m of media) { upsertMedia(m); targets.add(String(m.id)); }
  }
  const since = Math.max(lastRun - 5 * 60000, now() - 7 * 86400000); // 최근 미처리 댓글, 최대 7일
  let found = 0;
  for (const mediaId of targets) {
    let comments = [];
    try { comments = await ig.getComments(mediaId, 50); } catch (e) { logEvent('warn', 'poll', `댓글 조회 실패 (${mediaId}): ${e.message}`); continue; }
    for (const c of comments) {
      const t = c.timestamp ? new Date(c.timestamp).getTime() : now();
      if (t < since) continue;
      const seen = db.prepare('SELECT 1 FROM comments_seen WHERE comment_id = ?').get(String(c.id));
      if (seen) continue;
      found++;
      await handleComment({ account, source: 'poll', comment: { id: c.id, text: c.text, from: c.from || { username: c.username }, media: { id: mediaId }, parent_id: c.parent_id } });
    }
  }
  lastRun = now();
  if (found) logEvent('info', 'poll', `폴링으로 새 댓글 ${found}건 처리`);
}

export function startPoller() {
  if (!config.commentPolling || timer) return;
  const iv = Math.max(30, config.commentPollIntervalSec) * 1000;
  timer = setInterval(() => pollOnce().catch((e) => logEvent('error', 'poll', `폴링 오류: ${e.message}`)), iv);
  logEvent('info', 'poll', `댓글 폴링 시작 (${iv / 1000}초 간격)`);
}
export { pollOnce };
