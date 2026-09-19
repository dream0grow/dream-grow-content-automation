// 엔드투엔드 시뮬레이션: 서버를 MOCK 모드로 띄우고 Meta 웹훅 알림을 흉내내 전체 흐름을 검증합니다.
//   node test/simulate.js
import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PORT = 3999;
const SECRET = 'test-secret';
const BASE = `http://localhost:${PORT}`;
const DB = path.join(ROOT, 'data', 'test.sqlite');
for (const f of [DB, DB + '-wal', DB + '-shm']) if (fs.existsSync(f)) fs.unlinkSync(f);

const server = spawn(process.execPath, ['src/server.js'], {
  cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'],
  env: { ...process.env, MOCK_INSTAGRAM: '1', PORT: String(PORT), DB_PATH: DB, IG_APP_SECRET: SECRET, IG_APP_ID: 'test-app', DASHBOARD_PASSWORD: '', WEBHOOK_VERIFY_TOKEN: 'vt', PUBLIC_URL: BASE, COMMENT_POLLING: '0' },
});
let serverLog = '';
server.stdout.on('data', (d) => { serverLog += d; });
server.stderr.on('data', (d) => { serverLog += d; process.stderr.write(d); });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function api(method, p, body) {
  const r = await fetch(BASE + p, { method, headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  try { return JSON.parse(t); } catch { return t; }
}
async function webhook(body) {
  const raw = JSON.stringify(body);
  const sig = 'sha256=' + crypto.createHmac('sha256', SECRET).update(raw).digest('hex');
  const r = await fetch(BASE + '/webhook', { method: 'POST', headers: { 'content-type': 'application/json', 'x-hub-signature-256': sig }, body: raw });
  return r.json();
}
const IG_ID = '17841400000000001';
const commentEvent = (id, igsid, username, text, mediaId = 'media_1') => ({
  object: 'instagram', entry: [{ id: IG_ID, time: Date.now(), changes: [{ field: 'comments', value: { id, from: { id: igsid, username }, text, media: { id: mediaId, media_product_type: 'REELS' } } }] }],
});
const postbackEvent = (igsid, payload, title = '버튼') => ({
  object: 'instagram', entry: [{ id: IG_ID, time: Date.now(), messaging: [{ sender: { id: igsid }, recipient: { id: IG_ID }, timestamp: Date.now(), postback: { mid: 'mid-' + crypto.randomUUID(), title, payload } }] }],
});
const messageEvent = (igsid, text) => ({
  object: 'instagram', entry: [{ id: IG_ID, time: Date.now(), messaging: [{ sender: { id: igsid }, recipient: { id: IG_ID }, timestamp: Date.now(), message: { mid: 'mid-' + crypto.randomUUID(), text } }] }],
});

let pass = 0, fail = 0;
function check(name, cond, extra = '') {
  if (cond) { pass++; console.log(`  ✔ ${name}`); } else { fail++; console.log(`  ✘ ${name} ${extra}`); }
}
const calls = async () => api('GET', '/api/mock/calls');
const lastCall = async (kind) => (await calls()).filter((c) => c.kind === kind).pop();
const clearCalls = () => api('DELETE', '/api/mock/calls');
const leads = () => api('GET', '/api/leads');

try {
  // 서버 대기
  for (let i = 0; i < 50; i++) { try { await fetch(BASE + '/api/status'); break; } catch { await sleep(200); } }

  console.log('\n[0] 웹훅 검증(GET) & 서명 검사');
  const ch = await fetch(`${BASE}/webhook?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=12345`).then((r) => r.text());
  check('hub.challenge 응답', ch === '12345');
  const bad = await fetch(BASE + '/webhook', { method: 'POST', headers: { 'content-type': 'application/json', 'x-hub-signature-256': 'sha256=00' }, body: '{}' });
  check('잘못된 서명 401', bad.status === 401);

  console.log('\n[1] 계정 연결(mock) & 자동화 생성');
  const acc = await api('POST', '/api/mock/connect');
  check('계정 연결', acc && acc.username === 'dream_on_lee');
  await api('PUT', '/api/settings', { comment_reply_delay_min: 0, comment_reply_delay_max: 0, dm_hour_limit: 3600 });
  const auto = await api('POST', '/api/automations', {
    name: '수학 개념 로드맵', enabled: true, trigger_type: 'comment', post_scope: 'all', keyword_mode: 'contains', keywords: ['로드맵'],
    comment_reply_mode: 'general', dm_type: 'button', image_url: 'https://example.com/roadmap.png', title: '초등 수학 개념 로드맵', subtitle: '핵심 개념 지도를 확인해보세요.',
    buttons: [{ label: '수학 개념 로드맵 받기', reply: '[username] 님, 신청 감사합니다!\nhttps://drive.google.com/file/d/ABC/view' }], follow_gate: true,
  });
  check('자동화 생성 (팔로우 게이트 ON)', auto.id > 0 && auto.follow_gate === 1);
  const preview = await api('GET', `/api/automations/${auto.id}/preview`);
  check('첫 DM = generic 템플릿 + postback 버튼', preview.message?.attachment?.payload?.template_type === 'generic' && preview.message.attachment.payload.elements[0].buttons[0].type === 'postback' && preview.gated === true);

  console.log('\n[2] 댓글 → 대댓글 예약 + 버튼형 Private Reply');
  await clearCalls();
  const r1 = await webhook(commentEvent('c1', '1001', 'parent_kim', '로드맵 주세요!!'));
  check('댓글 매칭', r1.results?.[0]?.automation === auto.id, JSON.stringify(r1));
  await api('POST', '/api/tools/flush');
  const pr = await lastCall('sendPrivateReply');
  check('Private Reply(comment_id=c1) 로 템플릿 발송', pr?.commentId === 'c1' && pr.message.attachment?.payload?.template_type === 'generic');
  check('버튼 payload = LM:<id>:0', pr?.message.attachment.payload.elements[0].buttons[0].payload === `LM:${auto.id}:0`);
  const cr = await lastCall('replyToComment');
  check('자동 대댓글 게시 (@username 치환)', cr?.commentId === 'c1' && /@parent_kim|DM/.test(cr.text), cr?.text);
  let ld = (await leads()).find((l) => l.igsid === '1001');
  check('delivery 단계 = dm_sent', ld?.stage === 'dm_sent', ld?.stage);

  console.log('\n[3] ★ 팔로우 게이트: 비팔로워가 버튼 클릭 → 차단 + "팔로우했어요" 재시도 버튼');
  await clearCalls();
  await api('POST', '/api/mock/follow', { igsid: '1001', follows: false });
  await webhook(postbackEvent('1001', `LM:${auto.id}:0`));
  const gp = await lastCall('getUserProfile');
  check('is_user_follow_business 조회함', gp?.igsid === '1001' && gp.is_user_follow_business === false);
  const blockMsg = await lastCall('sendMessage');
  check('비팔로워 안내 + 재시도 버튼(RC) 발송', blockMsg?.message.attachment?.payload?.template_type === 'button' && blockMsg.message.attachment.payload.buttons[0].payload === `RC:${auto.id}:0` && /팔로우/.test(blockMsg.message.attachment.payload.text));
  check('리드마그넷 링크가 노출되지 않음', !JSON.stringify(blockMsg).includes('drive.google.com'));
  ld = (await leads()).find((l) => l.igsid === '1001');
  check('delivery 단계 = gate_blocked', ld?.stage === 'gate_blocked' && ld.is_follower === 0);

  console.log('\n[4] 재시도 클릭(아직 미팔로우) → 다시 차단');
  await clearCalls();
  await webhook(postbackEvent('1001', `RC:${auto.id}:0`, '팔로우했어요.'));
  const again = await lastCall('sendMessage');
  check('2회차 안내 문구 발송', /아직 팔로우가 확인되지/.test(again?.message.attachment?.payload?.text || ''));
  ld = (await leads()).find((l) => l.igsid === '1001');
  check('gate_attempts = 2', ld?.gate_attempts === 2);

  console.log('\n[5] 팔로우 후 재시도 → 리드마그넷 전송');
  await clearCalls();
  await api('POST', '/api/mock/follow', { igsid: '1001', follows: true });
  await webhook(postbackEvent('1001', `RC:${auto.id}:0`, '팔로우했어요.'));
  const deliver = await lastCall('sendMessage');
  check('리드마그넷 텍스트+링크 발송', deliver?.message.text?.includes('drive.google.com/file/d/ABC'));
  check('[username] 치환', deliver?.message.text?.startsWith('테스트유저01 님'), deliver?.message.text);
  ld = (await leads()).find((l) => l.igsid === '1001');
  check('delivery 단계 = delivered, is_follower=1', ld?.stage === 'delivered' && ld.is_follower === 1);
  const st = await api('GET', '/api/status');
  check('통계: gate_blocked 2, gate_converted 1, delivered 1', st.totals.gate_blocked === 2 && st.totals.gate_converted === 1 && st.totals.delivered === 1, JSON.stringify(st.totals));

  console.log('\n[6] 이미 팔로워인 사용자 → 버튼 클릭 즉시 전송');
  await clearCalls();
  await api('POST', '/api/mock/follow', { igsid: '1002', follows: true });
  await webhook(commentEvent('c2', '1002', 'follower_lee', '저도 로드맵 부탁드려요 🙏'));
  await api('POST', '/api/tools/flush');
  await webhook(postbackEvent('1002', `LM:${auto.id}:0`));
  const d2 = await lastCall('sendMessage');
  check('팔로워는 바로 링크 수신', d2?.igsid === '1002' && d2.message.text?.includes('drive.google.com'));

  console.log('\n[7] 키워드 불일치 / 내 댓글 / 중복 알림');
  await clearCalls();
  const r7 = await webhook(commentEvent('c3', '1003', 'someone', '영상 잘 봤어요'));
  check('키워드 불일치 → 무시', r7.results?.[0]?.skipped === 'nomatch');
  const r7b = await webhook(commentEvent('c4', IG_ID, 'dream_on_lee', '로드맵 DM 보냈어요'));
  check('내 계정 댓글 → 무시', r7b.results?.[0]?.skipped === 'self');
  const dupBody = commentEvent('c5', '1005', 'dup_user', '로드맵!');
  await webhook(dupBody); const r7c = await webhook(dupBody);
  check('동일 알림 재전송 → duplicate', r7c?.duplicate === true || r7c?.results?.[0]?.skipped === 'duplicate', JSON.stringify(r7c));

  console.log('\n[8] 템플릿 Private Reply 실패 → 텍스트 폴백 → 답장 시 게이트 진행');
  await clearCalls();
  await api('POST', '/api/mock/state', { failTemplatePrivateReply: true });
  await webhook(commentEvent('c6', '1006', 'fallback_user', '로드맵 원해요'));
  await api('POST', '/api/tools/flush');
  const fb = await lastCall('sendPrivateReply');
  check('폴백 텍스트 Private Reply 발송', fb?.message.text?.includes('받기'));
  ld = (await leads()).find((l) => l.igsid === '1006');
  check('delivery 단계 = awaiting_reply', ld?.stage === 'awaiting_reply', ld?.stage);
  await api('POST', '/api/mock/follow', { igsid: '1006', follows: false });
  await webhook(messageEvent('1006', '받기'));
  ld = (await leads()).find((l) => l.igsid === '1006');
  check('답장 후 비팔로워 → gate_blocked', ld?.stage === 'gate_blocked');
  await api('POST', '/api/mock/follow', { igsid: '1006', follows: true });
  await webhook(postbackEvent('1006', `RC:${auto.id}:0`));
  ld = (await leads()).find((l) => l.igsid === '1006');
  check('팔로우 후 → delivered', ld?.stage === 'delivered');
  await api('POST', '/api/mock/state', { failTemplatePrivateReply: false });

  console.log('\n[9] 게이트 OFF 텍스트형 자동화 → Private Reply 텍스트 즉시 발송');
  const auto2 = await api('POST', '/api/automations', { name: '텍스트형', enabled: true, trigger_type: 'comment', post_scope: 'selected', media_ids: ['media_3'], keyword_mode: 'exact', keywords: ['인생책목록'], comment_reply_mode: 'off', dm_type: 'text', dm_text: '[username] 님 책 목록입니다: https://example.com/books', follow_gate: false });
  await clearCalls();
  await webhook(commentEvent('c7', '1007', 'book_lover', '인생책목록 ✨', 'media_3'));
  await api('POST', '/api/tools/flush');
  const t9 = await lastCall('sendPrivateReply');
  check('텍스트 Private Reply (게이트 없음, exact+이모지 허용)', t9?.commentId === 'c7' && t9.message.text?.includes('example.com/books'));
  check('[username] 치환 + 발송 즉시 전달 완료 처리', t9?.message.text?.startsWith('book_lover 님') && (await leads()).find((l) => l.igsid === '1007')?.stage === 'delivered', t9?.message.text);
  const r9 = await webhook(commentEvent('c8', '1008', 'other', '인생책목록', 'media_1'));
  check('선택 게시물 외 댓글은 해당 자동화 미적용', r9.results?.[0]?.automation !== auto2.id);

  console.log('\n[10] 게시물별 시간당 대댓글 제한 + 오류 경고 감지 → 자동 중단');
  await webhook(commentEvent('c9', '1009', 'u9', '로드맵'));
  await api('POST', '/api/tools/flush');
  const q10 = await api('GET', '/api/status');
  check('media_1 시간당 4개 초과 → 5번째 대댓글은 보류(pending)', q10.queue.comment_pending === 1, JSON.stringify(q10.queue));
  await api('PUT', '/api/settings', { warning_threshold: 2, comment_reply_enabled: 1, comment_reply_post_hour_limit: 100 });
  await api('POST', '/api/mock/state', { failCommentReply: true });
  await api('POST', '/api/tools/flush');
  await webhook(commentEvent('c10', '1010', 'u10', '로드맵'));
  await api('POST', '/api/tools/flush');
  const s10 = await api('GET', '/api/settings');
  check('오류 2회 → comment_reply_enabled = 0 (자동 DM 은 계속)', s10.comment_reply_enabled === '0');
  const ev = await api('GET', '/api/events?limit=50');
  check('경고 이벤트 기록', ev.some((e) => e.type === 'comment_reply_disabled'));
  await api('POST', '/api/mock/state', { failCommentReply: false });

  console.log('\n[11] DM→DM 자동화 (DM 키워드)');
  await api('PUT', `/api/automations/${auto.id}`, { also_dm: true });
  await clearCalls();
  await api('POST', '/api/mock/follow', { igsid: '1011', follows: true });
  const r11 = await webhook(messageEvent('1011', '로드맵 받고 싶어요'));
  await api('POST', '/api/tools/flush');
  const d11 = await lastCall('sendMessage');
  check('DM 키워드 → 템플릿 DM 발송', r11.results?.[0]?.automation === auto.id && d11?.message.attachment?.payload?.template_type === 'generic');

  const csv = await fetch(BASE + '/api/leads?format=csv').then((r) => r.text());
  check('리드 CSV 내보내기', csv.replace(/^\ufeff/, '').startsWith('id,username') && csv.includes('tester_01'), csv.slice(0, 200));
} catch (e) {
  fail++; console.error('테스트 실행 오류:', e);
} finally {
  server.kill();
  console.log(`\n결과: ${pass} 통과, ${fail} 실패`);
  if (fail) { console.log('\n--- server log ---\n' + serverLog.slice(-4000)); process.exit(1); }
}
