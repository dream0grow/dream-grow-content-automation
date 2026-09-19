// 환경 변수 로딩 (.env 파일이 있으면 읽고, 이미 설정된 값은 덮어쓰지 않음)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..');

function loadDotEnv() {
  const file = path.join(ROOT, '.env');
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, 'utf8').split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) val = val.slice(1, -1);
    if (process.env[key] === undefined) process.env[key] = val;
  }
}
loadDotEnv();

const env = (k, d = '') => (process.env[k] === undefined || process.env[k] === '' ? d : process.env[k]);

export const config = {
  appId: env('IG_APP_ID'),
  appSecret: env('IG_APP_SECRET'),          // Instagram 앱 시크릿 (Business login settings)
  metaAppSecret: env('META_APP_SECRET'),    // (선택) Meta 앱 시크릿 (앱 설정 > 기본 설정). 웹훅 서명 검증 후보로 함께 사용
  publicUrl: env('PUBLIC_URL', 'http://localhost:3000').replace(/\/+$/, ''),
  verifyToken: env('WEBHOOK_VERIFY_TOKEN', 'change-me-verify-token'),
  dashboardPassword: env('DASHBOARD_PASSWORD', ''),
  port: Number(env('PORT', 3000)),
  dbPath: path.resolve(ROOT, env('DB_PATH', './data/autodm.sqlite')),
  apiVersion: env('IG_API_VERSION', 'v23.0'),
  commentPolling: env('COMMENT_POLLING', '0') === '1',
  commentPollIntervalSec: Number(env('COMMENT_POLL_INTERVAL_SEC', 120)),
  anthropicKey: env('ANTHROPIC_API_KEY'),
  mock: env('MOCK_INSTAGRAM', '0') === '1',
  scopes: ['instagram_business_basic', 'instagram_business_manage_messages', 'instagram_business_manage_comments'],
};

export const redirectUri = () => `${config.publicUrl}/auth/instagram/callback`;
export const webhookUrl = () => `${config.publicUrl}/webhook`;
