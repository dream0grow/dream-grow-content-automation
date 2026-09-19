// 장기 토큰(60일) 자동 갱신: 만료 10일 전부터 하루 한 번 갱신 시도
import { config } from './config.js';
import { db, getAccount, logEvent, now } from './db.js';
import { refreshLongLived } from './instagram.js';

export async function refreshIfNeeded(force = false) {
  const account = getAccount();
  if (!account || config.mock) return null;
  const left = (account.token_expires_at || 0) - now();
  const age = now() - (account.updated_at || account.connected_at || 0);
  if (!force && (left > 10 * 86400000 || age < 86400000)) return null; // 아직 여유 있음 / 24시간 미만은 갱신 불가
  try {
    const r = await refreshLongLived(account.access_token);
    db.prepare('UPDATE accounts SET access_token = ?, token_expires_at = ?, updated_at = ? WHERE id = ?')
      .run(r.access_token, now() + (r.expires_in || 5184000) * 1000, now(), account.id);
    logEvent('info', 'token_refresh', `액세스 토큰 갱신 완료 (만료까지 ${Math.round((r.expires_in || 0) / 86400)}일)`);
    return r;
  } catch (e) {
    logEvent('error', 'token_refresh', `토큰 갱신 실패: ${e.message}. 연결 페이지에서 다시 연결해 주세요.`);
    return null;
  }
}

export function startTokenRefresher() {
  setTimeout(() => refreshIfNeeded().catch(() => {}), 15000);
  setInterval(() => refreshIfNeeded().catch(() => {}), 6 * 3600000);
}
