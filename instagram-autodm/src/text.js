// 키워드 매칭 · 치환자 렌더링 · 대댓글 문구 풀 · (선택) AI 문구 변형
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config } from './config.js';
import { db, logEvent } from './db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const POOL_FILE = path.join(__dirname, 'replies-pool.json');

// ── 대댓글 풀 (기본 243개, KittyChat 일반 자동대댓글 목록과 동일한 스타일) ─────
export function loadReplyPool() {
  const row = db.prepare("SELECT value FROM settings WHERE key = 'reply_pool'").get();
  if (row) { try { const arr = JSON.parse(row.value); if (Array.isArray(arr) && arr.length) return arr; } catch {} }
  try { return JSON.parse(fs.readFileSync(POOL_FILE, 'utf8')); } catch { return ['@[username] DM 보내드렸어요. 확인 부탁드려요!']; }
}
export function saveReplyPool(arr) {
  const clean = (Array.isArray(arr) ? arr : []).map((s) => String(s).trim()).filter(Boolean);
  db.prepare("INSERT INTO settings(key, value) VALUES('reply_pool', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value").run(JSON.stringify(clean));
  return clean;
}

// 최근 N개와 겹치지 않게 무작위 선택 (같은 문구 반복 → 스팸 판정 위험 감소)
export function pickReply(pool, recent = []) {
  if (!pool.length) return null;
  const candidates = pool.filter((p) => !recent.includes(p));
  const list = candidates.length ? candidates : pool;
  return list[Math.floor(Math.random() * list.length)];
}

// ── 치환자 ─────────────────────────────────────────────────────────────
// [username] → 이름(없으면 아이디), @[username] → @아이디(멘션)
export function render(template, user = {}) {
  const username = user.username || '';
  const display = user.name || username || '고객';
  return String(template || '')
    .replace(/@\[username\]/gi, username ? `@${username}` : '')
    .replace(/\[username\]/gi, display)
    .replace(/\[today\]/gi, fmtDate(0)).replace(/\[tomorrow\]/gi, fmtDate(1))
    .replace(/\[1week\]/gi, fmtDate(7)).replace(/\[2weeks\]/gi, fmtDate(14)).replace(/\[3weeks\]/gi, fmtDate(21)).replace(/\[4weeks\]/gi, fmtDate(28));
}
function fmtDate(addDays) {
  const d = new Date(Date.now() + addDays * 86400000);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

// ── 키워드 매칭 ──────────────────────────────────────────────────────────
const EMOJI_RE = /[\p{Extended_Pictographic}\p{Emoji_Modifier}\p{Emoji_Component}\u200d\ufe0f]/gu;
export function normalize(s) {
  return String(s || '').toLowerCase().replace(EMOJI_RE, '').replace(/[\s\p{P}\p{S}]+/gu, '');
}
export function matchKeyword(text, automation, fuzzy = true) {
  const mode = automation.keyword_mode || 'contains';
  if (mode === 'any') return { matched: true, keyword: null };
  const keywords = (automation.keywords || []).map((k) => String(k).trim()).filter(Boolean);
  if (!keywords.length) return { matched: false, keyword: null };
  const nText = normalize(text);
  const loose = String(text || '').toLowerCase();
  for (const kw of keywords) {
    const nKw = normalize(kw);
    if (!nKw) continue;
    if (mode === 'exact') {
      if (nText === nKw) return { matched: true, keyword: kw };
      if (fuzzy && nText.includes(nKw) && nText.length <= nKw.length + 6) return { matched: true, keyword: kw }; // 키워드 + 약간의 이모지/감탄사 허용
    } else if (nText.includes(nKw) || loose.includes(kw.toLowerCase())) {
      return { matched: true, keyword: kw };
    }
  }
  return { matched: false, keyword: null };
}

// ── (선택) AI 문구 변형: 핵심 내용과 링크는 유지, 표현만 바꿈 ─────────────────
export async function aiVariation(text) {
  if (!config.anthropicKey || !text || text.length < 8) return text;
  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-api-key': config.anthropicKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-3-5-haiku-latest',
        max_tokens: 600,
        system: '너는 인스타그램 DM 문구를 살짝 바꿔 쓰는 도우미다. 규칙: 1) 의미·핵심 메시지·순서를 유지 2) URL, [username] 같은 대괄호 치환자, 줄바꿈 구조는 글자 하나 바꾸지 말고 그대로 둔다 3) 어휘·어미·이모지만 자연스럽게 다르게 4) 길이는 원문의 ±20% 5) 결과 문구만 출력(설명 금지).',
        messages: [{ role: 'user', content: text }],
      }),
    });
    if (!res.ok) throw new Error(`anthropic ${res.status}`);
    const j = await res.json();
    const out = (j.content || []).map((c) => c.text || '').join('').trim();
    // 링크가 그대로 살아있는지 검증. 아니면 원문 사용
    const urls = text.match(/https?:\/\/\S+/g) || [];
    if (!out || urls.some((u) => !out.includes(u))) return text;
    return out;
  } catch (e) {
    logEvent('warn', 'ai_variation', `AI 변형 실패, 원문 사용: ${e.message}`);
    return text;
  }
}
