# Instagram AutoDM — 팔로우 확인 · 리드마그넷 자동 전송 · 자동 대댓글

KittyChat(kittychat.ai)의 "자동 DM & 대댓글" 기능을 분석해 그대로 재구현한 **자체 호스팅** 인스타그램 자동화 서버입니다.
릴스/게시물에 키워드 댓글이 달리면 → 자동 대댓글을 달고 → 버튼형 DM을 보내고 → **팔로우한 사람에게만** 리드마그넷을 전송합니다.

- 외부 npm 의존성 **0개** (Node 22.13+ 내장 `node:sqlite`, `fetch`, `node:http` 만 사용)
- Meta 공식 **Instagram API with Instagram Login** 사용 (Facebook 페이지 불필요, KittyChat 과 동일 방식)
- 웹 대시보드 포함 (자동화 관리 · 리드 목록 · 안전장치 설정 · 활동 로그)

```
instagram-autodm/
├─ src/
│  ├─ server.js       HTTP 서버: 웹훅 · OAuth · 대시보드 API · 정적 파일
│  ├─ automation.js   ★ 핵심 흐름: 댓글 매칭 → 버튼 DM → 팔로우 확인 → 리드마그넷 전송
│  ├─ instagram.js    Graph API 클라이언트 (+ 개발용 Mock)
│  ├─ queues.js       DM/대댓글 발송 큐 · 시간당 제한 · 지연 · 경고 감지 자동 중단
│  ├─ webhook.js      Meta 웹훅 검증 · 서명 확인 · 이벤트 파싱
│  ├─ text.js         키워드 매칭 · [username] 치환 · 대댓글 문구 풀 · AI 문구 변형
│  ├─ poller.js       웹훅이 없을 때 댓글 폴링 폴백
│  ├─ tokens.js       60일 장기 토큰 자동 갱신
│  ├─ db.js           SQLite 스키마/헬퍼
│  └─ replies-pool.json  자동 대댓글 문구 243개 (KittyChat 일반 목록 스타일)
├─ public/            대시보드 (index.html, app.js, style.css)
├─ test/simulate.js   Mock 웹훅으로 전체 흐름 검증 (36개 시나리오)
├─ docs/kittychat-analysis.md   KittyChat 분석 기록
└─ .env.example
```

---

## 1. 작동 흐름 (KittyChat 과 동일)

```
[사용자] 릴스에 "로드맵" 댓글
   │  (Meta 웹훅: comments)
   ▼
[서버] 키워드 매칭 → ① 자동 대댓글 예약 (5~7분 지연, 문구 풀에서 무작위, @아이디 멘션)
                   → ② Private Reply 로 버튼형 DM 발송 (이미지·제목·부제목·[자료 받기] 버튼)
   │
   ▼  사용자가 [자료 받기] 버튼 클릭  (Meta 웹훅: messaging_postbacks)
[서버] ★ User Profile API 조회: is_user_follow_business ?
   ├─ true  → 버튼 속 메시지(리드마그넷 링크) 전송 → "전달 완료"
   └─ false → "팔로우 해주셨다면 아래 버튼을 눌러주세요" + [팔로우했어요.] 버튼
                 │  사용자가 팔로우 후 [팔로우했어요.] 클릭
                 ▼
              다시 확인 → true 면 리드마그넷 전송 ("팔로우 후 전환"으로 집계)
```

왜 이런 구조인가 (인스타그램 규칙):
- Private Reply(댓글 작성자에게 보내는 첫 DM)는 **댓글당 1회, 7일 이내**만 가능.
- 그 다음 메시지는 사용자가 **응답한 뒤 24시간** 안에만 보낼 수 있고, **버튼 클릭(postback)도 응답으로 인정**됨.
- 그래서 "첫 DM은 모두에게 → 버튼 클릭 시 팔로우 확인 → 팔로워에게만 내용 공개" 구조가 필요합니다.
- 팔로우 여부는 Instagram Messaging User Profile API 의 `is_user_follow_business` 필드로 정확히 확인합니다.

---

## 2. 설치부터 실제 작동까지 순서 (요약)

**서버는 반드시 인터넷에서 HTTPS 로 접근 가능한 주소에 24시간 떠 있어야 합니다.** Meta 가 댓글/버튼 클릭 알림을 그 주소로 보내고,
인스타그램 로그인 후 그 주소로 되돌려 보내기 때문입니다. 로컬에서만 띄우면 아무 일도 일어나지 않습니다.

```
① GitHub 에 코드 push
② Railway(추천) 에 배포 → https://xxxx.up.railway.app 주소 확보, 볼륨(/app/data) 붙이기
③ Meta 앱 생성 → 웹훅 URL · OAuth 리다이렉트 URI 등록 → Instagram 앱 ID/시크릿을 환경 변수에
④ 대시보드 "연결" 에서 인스타그램 로그인
⑤ 자동화 만들고 다른 계정으로 댓글 달아 테스트
```

클릭 단위의 상세 순서는 **[docs/deploy.md](docs/deploy.md)** 에 있습니다 (Railway 화면 기준, Fly.io/Render/내 Mac+터널 대안 포함).

---

## 2-1. 사전 준비

1. **인스타그램 프로페셔널 계정** (비즈니스 또는 크리에이터). 앱 → 프로필 → 메뉴 → 계정 유형 및 도구 → 프로페셔널 계정으로 전환.
2. 인스타그램 앱 → 설정 → 메시지 및 스토리 답장 → 메시지 요청 → **"메시지 접근 허용(Allow access to messages)" 켜기**. (꺼져 있으면 API 로 DM 을 보낼 수 없음)
3. ManyChat·KittyChat 등 다른 자동 DM 서비스와 **동시에 연결하지 마세요** (충돌). 이 서버로 옮길 때는 기존 서비스 연결을 먼저 끊으세요.
4. Node.js **22.13 이상** (`node -v`).
5. HTTPS 공개 주소 (배포 서버 또는 로컬 테스트용 `ngrok http 3000`).

---

## 3. Meta 앱 만들기 (한 번만)

서버가 먼저 배포되어 공개 주소가 있어야 합니다 (웹훅 검증 요청을 서버가 받아야 저장이 됨). 대시보드 **연결** 페이지에 등록할 값이 그대로 표시됩니다.

1. https://developers.facebook.com/apps → **앱 만들기** → 사용 사례 **"Instagram에서 메시지 및 콘텐츠 관리"** 선택.
2. 왼쪽 메뉴 **Instagram → API setup with Instagram business login** 로 이동. 여기에 번호 붙은 섹션이 있습니다.
3. **1. Generate access tokens** → Add account 로 본인 계정 추가 (공개 계정이어야 함). 이게 테스터 등록을 겸합니다.
   초대 수락이 필요하면 인스타그램 앱 → 설정 → 웹사이트 권한 → 테스터 초대 → 수락.
4. **2. Configure webhooks** → 콜백 URL `https://<내주소>/webhook`, 확인 토큰은 `.env` 의 `WEBHOOK_VERIFY_TOKEN` 과 동일하게 → Save.
   Manage 에서 구독 필드 **`comments`, `messages`, `messaging_postbacks`** 확인 (기본으로 켜져 있음).
5. **3. Set up Instagram business login** → Redirect URL 에 `https://<내주소>/auth/instagram/callback` → **Business login settings** 에서
   - **Instagram app ID / Instagram app secret** → `.env` 의 `IG_APP_ID`, `IG_APP_SECRET`. **앱 설정>기본 설정의 Meta 앱 ID 와는 다른 값입니다.**
   - Deauthorize callback URL `https://<내주소>/auth/instagram/deauthorize`, Data deletion request URL `https://<내주소>/auth/instagram/data-deletion`.
6. **앱 설정 → 기본 설정** 의 **앱 시크릿 코드**(Meta 앱 시크릿) → `.env` 의 `META_APP_SECRET`. 웹훅 서명이 두 시크릿 중 어느 쪽으로 와도 통과하도록 서버가 둘 다 검사합니다.
7. 권한(scope) 3개: `instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_manage_comments` (서버가 로그인 때 자동 요청).
   같은 페이지 **1. 필수 메시지 권한 추가 → Add all required permissions** 를 눌러 앱에 추가해 두어야 합니다.
8. **앱 게시(라이브)**: Webhooks 섹션에 "앱이 공개 상태여야 Webhooks 수신" 이라고 나옵니다. 개인정보처리방침 URL(`/privacy`) · 앱 아이콘 1024×1024 · 카테고리를 채우고 게시하세요.
   검수 전에는 앱에 역할이 있는 계정만 쓸 수 있으므로 본인 계정용으로는 그것으로 충분합니다.
   - 본인 계정만 쓸 거라면 이 상태(개발 모드)에서 동작합니다.
   - 여러 사람에게 서비스하려면 **앱 검수(App Review)** 로 위 3개 권한의 고급 액세스를 받고 앱을 **라이브** 로 전환해야 합니다.
   - 개발 모드에서 댓글 웹훅이 오지 않는 경우가 보고되어 있습니다. 그럴 땐 `.env` 에 `COMMENT_POLLING=1` 로 폴링 폴백을 켜세요 (2분 간격으로 최근 게시물 댓글을 직접 조회).

---

## 4. 설치 · 실행

```bash
cd instagram-autodm
cp .env.example .env      # 값 채우기
npm start                 # http://localhost:3000
```

로컬에서 실제 인스타그램과 연결해 보려면:
```bash
ngrok http 3000           # 나오는 https 주소를 .env 의 PUBLIC_URL 에 넣고 재시작
```

브라우저에서 `PUBLIC_URL` 접속 → (비밀번호: `DASHBOARD_PASSWORD`) → **연결** → "Instagram 으로 연결" → 권한 승인.
연결이 끝나면 서버가 자동으로 계정 단위 웹훅 구독(`/subscribed_apps`)까지 마칩니다.

### 자동화 만들기
1. **자동 DM & 대댓글** → **+ 자동화 추가**
2. 게시물: 전체 / 특정 게시물 선택 / "다음 발행 게시물에 적용"
3. 키워드: 포함 / 정확히 / 불특정(아무 댓글)
4. 대댓글: 일반(문구 풀 무작위) / 특정(이 자동화 전용 문구) / Off
5. DM: 버튼형(이미지·제목·부제목·버튼 최대 3개) 또는 텍스트
6. **🔒 '팔로워'에게만 버튼 속 메시지 공개** — 팔로우 확인 게이트 (기본 켜짐)
7. 버튼의 "클릭 시 보내는 메시지"에 리드마그넷 링크. `[username]` 은 상대 이름으로 치환.

### 개발/시연 모드 (인스타그램 없이)
```bash
npm run mock              # MOCK_INSTAGRAM=1 → API 호출 대신 기록만
npm test                  # 36개 시나리오 자동 검증 (팔로우 게이트 차단→전환, 폴백, 경고 감지 등)
```
MOCK 모드 대시보드의 "연결" 페이지에서 **모의 계정 연결** 을 누르면 화면을 둘러볼 수 있습니다.

---

## 5. 안전장치 (설정 페이지)

KittyChat 설정 화면과 동일한 항목이며 기본값도 같습니다.

| 항목 | 기본값 | 설명 |
|---|---|---|
| 비팔로워에게 보내는 메시지 | "댓글 남겨주셔서 감사합니다. ^_^ 저를 팔로우 해주셨다면 아래 버튼을 클릭해주세요!" | 팔로우 미확인 시 안내 |
| 재시도 버튼 레이블 | "팔로우했어요." | |
| 팔로우 확인 API 오류 시 | 엄격(차단) | 관대로 바꾸면 확인 실패해도 전송 |
| 시간당 자동 DM 제한 | 3600 | 발송 간격 = 3600 ÷ 값 (초) |
| 게시물별 시간당 대댓글 수 | 4 | 초과분은 10분 뒤 재시도 |
| 대댓글 지연 | 300~420초 | 댓글 직후 즉시 달지 않음 |
| 경고 감지 시 자동 대댓글 끄기 | 켜짐, 24시간 내 3회 | 오류 반복 시 대댓글만 중단, 자동 DM 은 계속 |
| 키워드 외 텍스트/이모지 허용 | 켜짐 | "로드맵!!🙏" 도 매칭 |

대댓글 문구 풀(243개)은 "일반 자동대댓글 문구" 버튼에서 편집할 수 있습니다. 문구가 다양할수록 스팸 판정 위험이 줄어듭니다.

---

## 6. 배포

클릭 단위 안내: **[docs/deploy.md](docs/deploy.md)** (Railway 기준. Fly.io / Render / 내 Mac+터널 대안 포함).

요점은 세 가지입니다.
- 항상 켜져 있는 프로세스가 필요 (지연 대댓글 큐, 며칠 뒤 눌리는 재시도 버튼). Vercel 같은 서버리스, Render 무료 플랜(15분 후 잠듦)은 부적합.
- SQLite 파일 하나가 전부이므로 **영구 볼륨**을 `/app/data` 에 붙이고 `DB_PATH=/app/data/autodm.sqlite`.
- 배포 후 생긴 주소를 `PUBLIC_URL` 에 넣고, 그 주소로 Meta 앱의 웹훅/리다이렉트를 등록.

**Docker (다른 서버에 직접 올릴 때)**
```bash
docker build -t instagram-autodm .
docker run -d --name autodm -p 3000:3000 --env-file .env -v $(pwd)/data:/app/data --restart unless-stopped instagram-autodm
```

---

## 7. API 요약 (대시보드가 사용하는 엔드포인트)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET/POST | `/webhook` | Meta 웹훅 검증 / 수신 (서명 `X-Hub-Signature-256` 검사) |
| GET | `/auth/instagram` → `/auth/instagram/callback` | OAuth 연결 |
| GET | `/api/status` | 계정·설정·큐·통계 |
| GET/PUT | `/api/settings` | 안전장치 설정 |
| GET/POST/PUT/DELETE | `/api/automations[/:id]` | 자동화 CRUD, `/:id/toggle`, `/:id/preview` |
| GET | `/api/media` | 게시물 목록 (10분 캐시, `?refresh=1`) |
| GET | `/api/leads` (`?format=csv`) | 리드/전달 이력 |
| GET | `/api/events` | 활동 로그 |
| GET/PUT | `/api/replies-pool` | 대댓글 문구 풀 |
| POST | `/api/tools/follow-check` `{igsid}` | ★ 팔로우 여부 즉시 조회 |
| POST | `/api/account/subscribe` | 웹훅 재구독 |

---

## 8. 자주 겪는 문제

- **DM 이 안 감**: 인스타그램 "메시지 접근 허용" 확인 → 대시보드 "연결"에서 웹훅 구독 상태 확인 → 활동 로그의 오류 코드 확인. 비팔로워에게 간 DM 은 "요청" 폴더에 들어가며 알림이 없습니다 (인스타그램 정책).
- **댓글 웹훅이 안 옴**: 앱이 개발 모드면 테스터 계정만 가능. `COMMENT_POLLING=1` 로 폴백 사용. 계정이 비공개면 댓글 웹훅이 오지 않습니다.
- **버튼형 Private Reply 거부**: 자동으로 텍스트 폴백("받기 라고 답장해 주세요")을 보내고, 답장이 오면 팔로우 확인 후 전송합니다.
- **대댓글이 갑자기 안 달림**: 경고 감지로 자동 중단된 상태. 지연을 300초 이상으로 올리고 3~5일 뒤 설정에서 다시 켜세요.
- **토큰 만료**: 60일 토큰은 자동 갱신됩니다. 비밀번호 변경 등으로 무효화되면 "다시 연결".
