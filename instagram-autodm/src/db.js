// SQLite 저장소 (Node 22.13+ 내장 node:sqlite 사용, 외부 의존성 없음)
import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { config } from './config.js';

fs.mkdirSync(path.dirname(config.dbPath), { recursive: true });
export const db = new DatabaseSync(config.dbPath);
db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');

db.exec(`
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ig_user_id TEXT UNIQUE NOT NULL,        -- 웹훅 entry.id 와 같은 프로페셔널 계정 ID
  app_scoped_id TEXT,
  username TEXT,
  name TEXT,
  profile_picture_url TEXT,
  followers_count INTEGER,
  access_token TEXT NOT NULL,
  token_expires_at INTEGER,
  webhook_subscribed INTEGER DEFAULT 0,
  connected_at INTEGER,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS automations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER,
  name TEXT NOT NULL,
  enabled INTEGER DEFAULT 1,
  trigger_type TEXT DEFAULT 'comment',     -- comment | dm
  also_dm INTEGER DEFAULT 0,               -- 댓글 자동화이지만 DM 속 키워드에도 반응
  post_scope TEXT DEFAULT 'all',           -- all | selected
  media_ids TEXT DEFAULT '[]',             -- JSON 배열
  apply_to_future INTEGER DEFAULT 0,       -- 다음 발행 게시물에도 적용
  keyword_mode TEXT DEFAULT 'contains',    -- any | contains | exact
  keywords TEXT DEFAULT '[]',              -- JSON 배열
  comment_reply_mode TEXT DEFAULT 'general', -- off | general | custom
  comment_replies TEXT DEFAULT '[]',       -- custom 일 때 문구 JSON 배열
  dm_type TEXT DEFAULT 'button',           -- text | button
  dm_text TEXT DEFAULT '',                 -- text 형 DM 본문 (900자)
  image_url TEXT DEFAULT '',
  title TEXT DEFAULT '',
  subtitle TEXT DEFAULT '',
  buttons TEXT DEFAULT '[]',               -- JSON [{label, reply, url}]
  follow_gate INTEGER DEFAULT 1,           -- 팔로워에게만 버튼 속 메시지 공개
  ai_variation INTEGER DEFAULT 0,
  send_count INTEGER DEFAULT 0,
  delivered_count INTEGER DEFAULT 0,
  created_at INTEGER,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS processed_events (
  key TEXT PRIMARY KEY,
  at INTEGER
);

CREATE TABLE IF NOT EXISTS comments_seen (
  comment_id TEXT PRIMARY KEY,
  media_id TEXT,
  igsid TEXT,
  username TEXT,
  text TEXT,
  automation_id INTEGER,
  matched INTEGER DEFAULT 0,
  received_at INTEGER
);

CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  automation_id INTEGER,
  igsid TEXT,
  username TEXT,
  name TEXT,
  source TEXT,                             -- comment | dm | poll
  comment_id TEXT,
  media_id TEXT,
  stage TEXT,                              -- dm_sent | awaiting_reply | gate_blocked | delivered | failed
  gate_attempts INTEGER DEFAULT 0,
  is_follower INTEGER,
  follower_count INTEGER,
  button_index INTEGER,
  last_error TEXT,
  created_at INTEGER,
  updated_at INTEGER,
  delivered_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_deliveries_igsid ON deliveries(igsid, automation_id);

CREATE TABLE IF NOT EXISTS comment_reply_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  comment_id TEXT,
  media_id TEXT,
  igsid TEXT,
  username TEXT,
  automation_id INTEGER,
  text TEXT,
  run_at INTEGER,
  status TEXT DEFAULT 'pending',           -- pending | done | failed | dropped
  attempts INTEGER DEFAULT 0,
  error TEXT,
  created_at INTEGER,
  done_at INTEGER
);

CREATE TABLE IF NOT EXISTS dm_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  delivery_id INTEGER,
  kind TEXT,                               -- private_reply | message
  igsid TEXT,
  comment_id TEXT,
  payload TEXT,                            -- JSON message 객체
  fallback_payload TEXT,                   -- 템플릿 실패 시 대체 메시지 JSON
  final INTEGER DEFAULT 0,                 -- 1이면 이 메시지 자체가 리드마그넷(게이트 없는 텍스트 DM) → 발송 성공 = 전달 완료
  run_at INTEGER,
  status TEXT DEFAULT 'pending',
  attempts INTEGER DEFAULT 0,
  error TEXT,
  created_at INTEGER,
  done_at INTEGER
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  level TEXT,                              -- info | warn | error
  type TEXT,
  message TEXT,
  data TEXT,
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS stats_daily (
  date TEXT PRIMARY KEY,
  comments INTEGER DEFAULT 0,
  dm_sent INTEGER DEFAULT 0,
  gate_checks INTEGER DEFAULT 0,
  gate_blocked INTEGER DEFAULT 0,
  gate_converted INTEGER DEFAULT 0,
  delivered INTEGER DEFAULT 0,
  comment_replies INTEGER DEFAULT 0,
  errors INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS media_cache (
  id TEXT PRIMARY KEY,
  caption TEXT,
  media_type TEXT,
  media_product_type TEXT,
  thumbnail_url TEXT,
  permalink TEXT,
  timestamp TEXT,
  fetched_at INTEGER
);
`);

// 기존 DB 마이그레이션 (컴럼 추가)
try { db.exec('ALTER TABLE dm_queue ADD COLUMN final INTEGER DEFAULT 0'); } catch {}

// 오래된 기록 정리
export function cleanupOld() {
  db.prepare('DELETE FROM processed_events WHERE at < ?').run(now() - 7 * 86400000);
  db.prepare('DELETE FROM comments_seen WHERE received_at < ?').run(now() - 30 * 86400000);
  db.prepare('DELETE FROM events WHERE created_at < ?').run(now() - 90 * 86400000);
  db.prepare("DELETE FROM dm_queue WHERE status != 'pending' AND created_at < ?").run(now() - 30 * 86400000);
  db.prepare("DELETE FROM comment_reply_queue WHERE status != 'pending' AND created_at < ?").run(now() - 30 * 86400000);
}

// ── 기본 설정 (KittyChat 설정 화면과 동일한 항목) ─────────────────────────
export const DEFAULT_SETTINGS = {
  master_switch: '1',
  non_follower_message: '댓글 남겨주셔서 감사합니다. ^_^ 저를 팔로우 해주셨다면 아래 버튼을 클릭해주세요!',
  follow_retry_button_label: '팔로우했어요.',
  follow_still_not_message: '아직 팔로우가 확인되지 않아요. 프로필에서 팔로우 버튼을 누른 뒤 다시 아래 버튼을 눌러주세요!',
  gate_fail_open: '0',                 // 팔로우 확인 API 실패 시 1이면 통과, 0이면 차단(엄격)
  dm_hour_limit: '3600',               // 시간당 자동 DM 전송 제한 (간격 = 3600/limit 초)
  comment_reply_enabled: '1',
  comment_reply_post_hour_limit: '4',  // 게시물 별 시간당 자동 대댓글 수
  comment_reply_delay_min: '300',      // 대댓글 지연 최소(초)
  comment_reply_delay_max: '420',      // 대댓글 지연 최대(초)
  auto_disable_on_warnings: '1',
  warning_threshold: '3',              // 24시간 내 대댓글 오류 N회면 대댓글 자동 중단
  keyword_fuzzy: '1',                  // 키워드 외 텍스트/이모지 있어도 매칭
  text_dm_reply_keyword: '받기',        // 템플릿 전송 실패 폴백: 이 단어로 답장하면 계속 진행
  fallback_prompt_message: '댓글 감사합니다! 자료를 받으시려면 이 메시지에 "받기" 라고 답장해 주세요 :)',
  delivered_followup: '',              // 리드마그넷 전송 후 추가 안내(비우면 없음)
};

export function getSetting(key) {
  const row = db.prepare('SELECT value FROM settings WHERE key = ?').get(key);
  return row ? row.value : DEFAULT_SETTINGS[key];
}
export function getSettings() {
  const out = { ...DEFAULT_SETTINGS };
  for (const r of db.prepare('SELECT key, value FROM settings').all()) out[r.key] = r.value;
  return out;
}
export function setSettings(obj) {
  const up = db.prepare('INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value');
  for (const [k, v] of Object.entries(obj)) {
    if (!(k in DEFAULT_SETTINGS)) continue;
    up.run(k, String(v));
  }
}
export const settingNum = (k) => Number(getSetting(k));
export const settingOn = (k) => getSetting(k) === '1' || getSetting(k) === 'true';

// ── 공용 헬퍼 ─────────────────────────────────────────────────────────────
export const now = () => Date.now();
export const today = () => new Date().toISOString().slice(0, 10);

export function logEvent(level, type, message, data) {
  db.prepare('INSERT INTO events(level, type, message, data, created_at) VALUES(?,?,?,?,?)')
    .run(level, type, message, data ? JSON.stringify(data) : null, now());
  const tag = level === 'error' ? '✖' : level === 'warn' ? '⚠' : '·';
  console.log(`${tag} [${type}] ${message}`);
  if (level === 'error') bumpStat('errors');
}

export function bumpStat(col, n = 1) {
  const d = today();
  db.prepare(`INSERT INTO stats_daily(date, ${col}) VALUES(?, ?) ON CONFLICT(date) DO UPDATE SET ${col} = ${col} + excluded.${col}`).run(d, n);
}

export function markProcessed(key) {
  try {
    db.prepare('INSERT INTO processed_events(key, at) VALUES(?, ?)').run(key, now());
    return true; // 처음 봄
  } catch {
    return false; // 중복
  }
}

export function getAccount() {
  return db.prepare('SELECT * FROM accounts ORDER BY id DESC LIMIT 1').get() || null;
}

const AUTOMATION_JSON = ['media_ids', 'keywords', 'comment_replies', 'buttons'];
export function parseAutomation(row) {
  if (!row) return null;
  const a = { ...row };
  for (const k of AUTOMATION_JSON) {
    try { a[k] = JSON.parse(a[k] || '[]'); } catch { a[k] = []; }
  }
  return a;
}
export function listAutomations() {
  return db.prepare('SELECT * FROM automations ORDER BY id DESC').all().map(parseAutomation);
}
export function getAutomation(id) {
  return parseAutomation(db.prepare('SELECT * FROM automations WHERE id = ?').get(id));
}
export function saveAutomation(input, id = null) {
  const a = {
    name: String(input.name || '').trim() || '이름 없는 자동화',
    enabled: input.enabled ? 1 : 0,
    trigger_type: input.trigger_type === 'dm' ? 'dm' : 'comment',
    also_dm: input.also_dm ? 1 : 0,
    post_scope: input.post_scope === 'selected' ? 'selected' : 'all',
    media_ids: JSON.stringify(Array.isArray(input.media_ids) ? input.media_ids.map(String) : []),
    apply_to_future: input.apply_to_future ? 1 : 0,
    keyword_mode: ['any', 'contains', 'exact'].includes(input.keyword_mode) ? input.keyword_mode : 'contains',
    keywords: JSON.stringify((Array.isArray(input.keywords) ? input.keywords : String(input.keywords || '').split(','))
      .map((s) => String(s).trim()).filter(Boolean)),
    comment_reply_mode: ['off', 'general', 'custom'].includes(input.comment_reply_mode) ? input.comment_reply_mode : 'general',
    comment_replies: JSON.stringify((Array.isArray(input.comment_replies) ? input.comment_replies : []).map((s) => String(s).trim()).filter(Boolean)),
    dm_type: input.dm_type === 'text' ? 'text' : 'button',
    dm_text: String(input.dm_text || '').slice(0, 900),
    image_url: String(input.image_url || '').trim(),
    title: String(input.title || '').slice(0, 80),
    subtitle: String(input.subtitle || '').slice(0, 80),
    buttons: JSON.stringify((Array.isArray(input.buttons) ? input.buttons : []).slice(0, 3)
      .map((b) => ({ label: String(b.label || '').slice(0, 20), reply: String(b.reply || '').slice(0, 900), url: String(b.url || '').trim() }))
      .filter((b) => b.label)),
    follow_gate: input.follow_gate ? 1 : 0,
    ai_variation: input.ai_variation ? 1 : 0,
    updated_at: now(),
  };
  if (id) {
    const sets = Object.keys(a).map((k) => `${k} = ?`).join(', ');
    db.prepare(`UPDATE automations SET ${sets} WHERE id = ?`).run(...Object.values(a), id);
    return getAutomation(id);
  }
  a.created_at = now();
  const cols = Object.keys(a).join(', ');
  const qs = Object.keys(a).map(() => '?').join(', ');
  const r = db.prepare(`INSERT INTO automations(${cols}) VALUES(${qs})`).run(...Object.values(a));
  return getAutomation(Number(r.lastInsertRowid));
}

export function findDelivery(automationId, igsid) {
  return db.prepare('SELECT * FROM deliveries WHERE automation_id = ? AND igsid = ? ORDER BY id DESC LIMIT 1').get(automationId, igsid) || null;
}
export function createDelivery(d) {
  const r = db.prepare(`INSERT INTO deliveries(automation_id, igsid, username, name, source, comment_id, media_id, stage, created_at, updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?)`).run(d.automation_id, d.igsid, d.username || null, d.name || null, d.source, d.comment_id || null, d.media_id || null, d.stage || 'queued', now(), now());
  return Number(r.lastInsertRowid);
}
export function updateDelivery(id, patch) {
  const keys = Object.keys(patch);
  if (!keys.length) return;
  db.prepare(`UPDATE deliveries SET ${keys.map((k) => `${k} = ?`).join(', ')}, updated_at = ? WHERE id = ?`).run(...keys.map((k) => patch[k]), now(), id);
}
