// Instagram API with Instagram Login (graph.instagram.com) 클라이언트
// 참고: KittyChat 도 동일한 로그인 방식(enable_fb_login=false)과 동일한 3개 권한을 사용합니다.
import { config, redirectUri } from './config.js';

const GRAPH = 'https://graph.instagram.com';
const OAUTH = 'https://api.instagram.com/oauth';

export class InstagramApiError extends Error {
  constructor(message, { status, code, subcode, type, fbtrace, body } = {}) {
    super(message);
    this.name = 'InstagramApiError';
    this.status = status; this.code = code; this.subcode = subcode; this.type = type; this.fbtrace = fbtrace; this.body = body;
  }
}

async function graphFetch(url, init = {}) {
  const res = await fetch(url, init);
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
  if (!res.ok || (body && body.error)) {
    const e = body?.error || {};
    throw new InstagramApiError(e.message || `HTTP ${res.status}`, {
      status: res.status, code: e.code, subcode: e.error_subcode, type: e.type, fbtrace: e.fbtrace_id, body,
    });
  }
  return body;
}

// ── OAuth ────────────────────────────────────────────────────────────────
export function authorizeUrl(state = '') {
  const p = new URLSearchParams({
    enable_fb_login: '0',
    force_reauth: 'true',
    client_id: config.appId,
    redirect_uri: redirectUri(),
    response_type: 'code',
    scope: config.scopes.join(','),
    state,
  });
  return `https://www.instagram.com/oauth/authorize?${p.toString()}`;
}

export async function exchangeCode(code) {
  const form = new URLSearchParams({
    client_id: config.appId,
    client_secret: config.appSecret,
    grant_type: 'authorization_code',
    redirect_uri: redirectUri(),
    code: code.replace(/#_$/, ''),
  });
  // → { access_token(단기, 1시간), user_id, permissions }
  return graphFetch(`${OAUTH}/access_token`, { method: 'POST', body: form });
}

export async function exchangeLongLived(shortToken) {
  const p = new URLSearchParams({ grant_type: 'ig_exchange_token', client_secret: config.appSecret, access_token: shortToken });
  // → { access_token(60일), token_type, expires_in }
  return graphFetch(`${GRAPH}/access_token?${p}`);
}

export async function refreshLongLived(longToken) {
  const p = new URLSearchParams({ grant_type: 'ig_refresh_token', access_token: longToken });
  return graphFetch(`${GRAPH}/refresh_access_token?${p}`);
}

// ── API 클라이언트 ──────────────────────────────────────────────────────────
export class InstagramClient {
  constructor(accessToken, igUserId = 'me') {
    this.token = accessToken;
    this.igUserId = igUserId || 'me';
    this.v = config.apiVersion;
  }
  url(path, params = {}) {
    const u = new URL(`${GRAPH}/${this.v}/${path.replace(/^\//, '')}`);
    for (const [k, val] of Object.entries(params)) if (val !== undefined && val !== null) u.searchParams.set(k, val);
    return u.toString();
  }
  headers() { return { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' }; }
  get(path, params) { return graphFetch(this.url(path, params), { headers: this.headers() }); }
  post(path, body, params) { return graphFetch(this.url(path, params), { method: 'POST', headers: this.headers(), body: body ? JSON.stringify(body) : undefined }); }

  // 내 계정 정보. user_id 가 웹훅 entry.id 와 같은 프로페셔널 계정 ID
  getMe() { return this.get('me', { fields: 'id,user_id,username,name,profile_picture_url,followers_count,account_type' }); }

  // 게시물/릴스 목록 (자동화 게시물 선택용)
  async getMedia(limit = 50) {
    const r = await this.get('me/media', { fields: 'id,caption,media_type,media_product_type,thumbnail_url,media_url,permalink,timestamp', limit });
    return r.data || [];
  }
  async getComments(mediaId, limit = 50) {
    const r = await this.get(`${mediaId}/comments`, { fields: 'id,text,timestamp,username,from,parent_id', limit });
    return r.data || [];
  }

  // ★ 팔로우 여부 확인 (User Profile API)
  //   is_user_follow_business : 상대가 나를 팔로우하는지
  //   is_business_follow_user : 내가 상대를 팔로우하는지
  getUserProfile(igsid) {
    return this.get(String(igsid), { fields: 'name,username,profile_pic,follower_count,is_user_follow_business,is_business_follow_user,is_verified_user' });
  }

  // 댓글 작성자에게 Private Reply (댓글당 1회, 댓글 후 7일 이내)
  sendPrivateReply(commentId, message) {
    return this.post(`${this.igUserId}/messages`, { recipient: { comment_id: String(commentId) }, message });
  }
  // 일반 DM (상대가 응답한 뒤 24시간 안에서만 가능. 버튼 클릭(postback)도 응답으로 간주)
  sendMessage(igsid, message) {
    return this.post(`${this.igUserId}/messages`, { recipient: { id: String(igsid) }, message });
  }
  // 공개 대댓글
  replyToComment(commentId, text) {
    return this.post(`${commentId}/replies`, null, { message: text });
  }
  // 계정 단위 웹훅 구독 (앱 대시보드 구독과 별개로 반드시 호출해야 알림이 옴)
  subscribeWebhooks(fields = ['comments', 'messages', 'messaging_postbacks']) {
    return this.post(`${this.igUserId}/subscribed_apps`, null, { subscribed_fields: fields.join(',') });
  }
  getSubscribedApps() { return this.get(`${this.igUserId}/subscribed_apps`); }
}

// ── 메시지 빌더 ───────────────────────────────────────────────────────────
export const msg = {
  text: (text) => ({ text: String(text).slice(0, 1000) }),
  // 이미지+제목+부제목+버튼 (KittyChat '버튼형 템플릿')
  generic: ({ title, subtitle, image_url, buttons }) => ({
    attachment: {
      type: 'template',
      payload: {
        template_type: 'generic',
        elements: [{
          title: String(title || ' ').slice(0, 80),
          ...(subtitle ? { subtitle: String(subtitle).slice(0, 80) } : {}),
          ...(image_url ? { image_url } : {}),
          buttons: buttons.slice(0, 3),
        }],
      },
    },
  }),
  // 텍스트+버튼 (이미지 없음, 텍스트 640자)
  button: (text, buttons) => ({
    attachment: { type: 'template', payload: { template_type: 'button', text: String(text).slice(0, 640), buttons: buttons.slice(0, 3) } },
  }),
  postback: (title, payload) => ({ type: 'postback', title: String(title).slice(0, 20), payload: String(payload).slice(0, 1000) }),
  webUrl: (title, url) => ({ type: 'web_url', title: String(title).slice(0, 20), url }),
};

// ── 개발용 목(Mock) 클라이언트 ─────────────────────────────────────────────
// MOCK_INSTAGRAM=1 이면 API 를 호출하지 않고 호출 내역을 기록합니다. 팔로우 상태는 mockState.follow 로 제어.
export const mockState = { calls: [], follow: {}, failTemplatePrivateReply: false, failCommentReply: false };
export class MockInstagramClient extends InstagramClient {
  record(kind, data) { const rec = { kind, at: Date.now(), ...data }; mockState.calls.push(rec); if (mockState.calls.length > 500) mockState.calls.shift(); return rec; }
  async getMe() { return { id: 'app-scoped-1', user_id: '17841400000000001', username: 'dream_on_lee', name: '드림그로우 (모의)', followers_count: 12345, account_type: 'MEDIA_CREATOR' }; }
  async getMedia() {
    return [
      { id: 'media_1', caption: '아무댓글 주시면 “수학 개념 로드맵” 자료 바로 드려요', media_type: 'VIDEO', media_product_type: 'REELS', permalink: 'https://instagram.com/reel/mock1', timestamp: new Date().toISOString() },
      { id: 'media_2', caption: '진짜 자기 주도 학습의 비밀 - 댓글에 "자기주도학습" 남겨주세요', media_type: 'VIDEO', media_product_type: 'REELS', permalink: 'https://instagram.com/reel/mock2', timestamp: new Date().toISOString() },
      { id: 'media_3', caption: '초등 필독서 80권 목록 나눔 - "인생책목록"', media_type: 'IMAGE', media_product_type: 'FEED', permalink: 'https://instagram.com/p/mock3', timestamp: new Date().toISOString() },
    ];
  }
  async getComments() { return []; }
  async getUserProfile(igsid) {
    const follows = !!mockState.follow[String(igsid)];
    this.record('getUserProfile', { igsid, is_user_follow_business: follows });
    return { name: `테스트유저${String(igsid).slice(-2)}`, username: `tester_${String(igsid).slice(-2)}`, follower_count: 42, is_user_follow_business: follows, is_business_follow_user: false };
  }
  async sendPrivateReply(commentId, message) {
    if (mockState.failTemplatePrivateReply && message.attachment) {
      this.record('sendPrivateReply:FAIL', { commentId, message });
      throw new InstagramApiError('(#100) Unsupported message for private reply', { code: 100, status: 400 });
    }
    this.record('sendPrivateReply', { commentId, message });
    return { recipient_id: 'igsid-from-' + commentId, message_id: 'mid-' + Math.random().toString(36).slice(2) };
  }
  async sendMessage(igsid, message) { this.record('sendMessage', { igsid, message }); return { recipient_id: igsid, message_id: 'mid-' + Math.random().toString(36).slice(2) }; }
  async replyToComment(commentId, text) {
    if (mockState.failCommentReply) { this.record('replyToComment:FAIL', { commentId, text }); throw new InstagramApiError('(#368) The action attempted has been deemed abusive or is otherwise disallowed', { code: 368, status: 400 }); }
    this.record('replyToComment', { commentId, text }); return { id: 'reply-' + Math.random().toString(36).slice(2) };
  }
  async subscribeWebhooks(fields) { this.record('subscribeWebhooks', { fields }); return { success: true }; }
  async getSubscribedApps() { return { data: [{ subscribed_fields: ['comments', 'messages', 'messaging_postbacks'] }] }; }
}

export function clientFor(account) {
  if (config.mock) return new MockInstagramClient(account?.access_token || 'mock', account?.ig_user_id || 'me');
  return new InstagramClient(account.access_token, account.ig_user_id || 'me');
}
