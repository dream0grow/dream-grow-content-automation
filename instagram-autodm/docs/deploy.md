# 배포 가이드 (처음부터 끝까지)

이 서버는 **인터넷에서 HTTPS 로 접근 가능한 주소**에 24시간 떠 있어야 합니다. 이유는 두 가지입니다.

1. Meta 가 댓글/버튼 클릭 알림(웹훅)을 **우리 서버로 직접 보내기** 때문 → 주소가 없으면 아무 일도 일어나지 않음
2. 인스타그램 로그인 후 Meta 가 사용자를 **우리 서버 주소로 되돌려 보내기** 때문 (OAuth redirect)

또 자동 대댓글은 5~7분 뒤에 달리고, 팔로우 재확인 버튼은 며칠 뒤에 눌릴 수도 있어서 **항상 켜져 있는 프로세스**가 필요합니다.
그래서 Vercel 같은 서버리스는 맞지 않고, Railway(추천) / Fly.io / Render(유료) / 내 컴퓨터+터널 중 하나를 씁니다.

전체 순서:

```
① GitHub 에 코드 올리기 → ② Railway 에 배포 (공개 https 주소 얻기) → ③ Meta 앱 만들고 주소 등록
→ ④ 대시보드에서 인스타그램 연결 → ⑤ 자동화 만들고 테스트
```

소요 시간 약 30~40분. 비용: Railway Hobby 월 $5 (사용량 포함).

---

## ① GitHub 에 코드 올리기

이 폴더(`instagram-autodm/`)는 `dream-grow-content-automation` 저장소 안에 있습니다. 그대로 커밋해서 push 하면 됩니다.
(`.env` 와 `data/` 는 `.gitignore` 에 있어 올라가지 않습니다.)

```bash
# Mac 에서 git 이 "Xcode license" 오류를 내면 먼저 한 번:
sudo xcodebuild -license accept

cd ~/Documents/dream-grow-content-automation
git add instagram-autodm
git commit -m "feat: Instagram AutoDM (팔로우 확인 게이트 + 리드마그넷 + 자동 대댓글)"
git push
```

> 저장소 전체를 올리기 싫으면 `instagram-autodm` 폴더만 새 저장소로 만들어도 됩니다. 그 경우 아래 "Root Directory" 단계는 건너뜁니다.

---

## ② Railway 배포 (추천)

1. https://railway.app 가입 (GitHub 로그인) → 결제 정보 등록 후 **Hobby 플랜**.
2. **New Project → Deploy from GitHub repo** → `dream-grow-content-automation` 선택.
   (처음이면 "Configure GitHub App" 으로 저장소 접근 권한을 줘야 합니다.)
3. 생성된 서비스 카드를 클릭 → **Settings** 탭:
   - **Source → Root Directory** 에 `instagram-autodm` 입력. (모노레포라 이 폴더만 빌드하도록)
   - Railway 가 폴더 안의 `Dockerfile` 을 자동으로 사용합니다. 빌드 로그에 `Using detected Dockerfile!` 이 뜨면 정상.
   - **Deploy → App Sleeping(서버리스)** 옵션이 있으면 **끄기**. (자면 웹훅을 놓칩니다)
4. **Variables** 탭 → **Raw Editor** → 아래 내용을 붙여넣고 값 채우기 (아직 모르는 값은 ③에서 채움):
   ```
   IG_APP_ID=
   IG_APP_SECRET=
   META_APP_SECRET=
   PUBLIC_URL=https://임시
   WEBHOOK_VERIFY_TOKEN=아무긴문자열_예_growcircle-verify-2026
   DASHBOARD_PASSWORD=대시보드비밀번호
   DB_PATH=/app/data/autodm.sqlite
   COMMENT_POLLING=0
   ```
   `PORT` 는 Railway 가 자동으로 넣어주므로 적지 않습니다.
5. **볼륨 추가** (DB 가 재배포 때 날아가지 않게):
   프로젝트 캔버스에서 서비스 우클릭(또는 `⌘K`) → **Add Volume** → 서비스에 연결 → **Mount path** `/app/data`.
6. **Settings → Networking → Generate Domain** → `https://xxxx.up.railway.app` 같은 주소가 생깁니다. 복사.
7. Variables 로 돌아가 `PUBLIC_URL=https://xxxx.up.railway.app` (끝에 `/` 없이) 로 수정 → 자동 재배포.
8. 확인: 브라우저에서 `https://xxxx.up.railway.app/healthz` → `{"ok":true,...}` 가 보이면 서버가 살아 있는 것.
   `https://xxxx.up.railway.app/` 은 대시보드 (아이디 아무거나 + `DASHBOARD_PASSWORD`).

이제 Meta 에 등록할 두 주소가 정해졌습니다. 대시보드 **연결** 페이지에도 똑같이 표시됩니다.

| 용도 | 값 |
|---|---|
| OAuth 리다이렉트 URI | `https://xxxx.up.railway.app/auth/instagram/callback` |
| 웹훅 콜백 URL | `https://xxxx.up.railway.app/webhook` |
| 연결 해제 콜백 URL | `https://xxxx.up.railway.app/auth/instagram/deauthorize` |
| 데이터 삭제 요청 URL | `https://xxxx.up.railway.app/auth/instagram/data-deletion` |
| 개인정보처리방침 URL | `https://xxxx.up.railway.app/privacy` |

---

## ③ Meta 앱 만들기 & 주소 등록

### 3-1. 앱 생성
1. https://developers.facebook.com/apps → 오른쪽 위 **앱 만들기(Create App)**.
2. 사용 사례에서 **"Instagram에서 메시지 및 콘텐츠 관리"** (Manage messaging & content on Instagram) 선택 → 다음.
3. 앱 이름(예: `GrowCircle AutoDM`), 연락 이메일 입력 → 앱 만들기. (비즈니스 포트폴리오는 "없음/나중에" 가능)

### 3-2. Instagram 제품 설정 페이지로
왼쪽 메뉴 **Instagram → API setup with Instagram business login** (한국어: *Instagram 비즈니스 로그인을 통한 API 설정*).
이 페이지에 번호가 붙은 3~4개 섹션이 있습니다.

**1. Generate access tokens (액세스 토큰 생성)**
- **Add account** → 본인 인스타그램 프로페셔널 계정으로 로그인해 추가. (계정은 **공개** 여야 함)
- 이렇게 추가된 계정은 자동으로 "Instagram 테스터"가 되어 앱이 개발 모드여도 사용할 수 있습니다.
- 초대 수락이 필요하다고 나오면: 인스타그램 앱 → 프로필 → ☰ → 설정 → **웹사이트 권한(Apps and websites) → 테스터 초대(Tester invites) → 수락**.

**2. Configure webhooks (웹훅 설정)**
- **Configure** → Callback URL 에 `https://xxxx.up.railway.app/webhook`, Verify token 에 Railway 에 넣은 `WEBHOOK_VERIFY_TOKEN` 값 → **Save**.
  서버가 떠 있어야 즉시 검증에 성공합니다. (실패하면 Railway 로그와 값 오타 확인)
- 저장 후 **Manage** 로 들어가 구독 필드에 **`comments`, `messages`, `messaging_postbacks`** 가 체크되어 있는지 확인. (기본으로 전부 구독되어 있음)

**3. Set up Instagram business login (비즈니스 로그인 설정)**
- **Set up** → Redirect URL 에 `https://xxxx.up.railway.app/auth/instagram/callback` → Save.
- **Business login settings** 클릭 → 여기에 **Instagram app ID** 와 **Instagram app secret** 이 있습니다.
  이 두 값을 Railway Variables 의 `IG_APP_ID`, `IG_APP_SECRET` 에 넣으세요. **(앱 설정 > 기본 설정의 Meta 앱 ID 와 다른 값입니다!)**
- 같은 화면에서 **Deauthorize callback URL** `…/auth/instagram/deauthorize`, **Data deletion request URL** `…/auth/instagram/data-deletion` 입력 → Save.
  (이 두 칸이 비어 있으면 저장이 안 되는 경우가 있습니다)

### 3-3. Meta 앱 시크릿도 넣기
왼쪽 메뉴 **앱 설정(App settings) → 기본 설정(Basic)** → **앱 시크릿 코드** 표시 → Railway `META_APP_SECRET` 에 입력.
같은 화면의 **개인정보처리방침 URL** 에 `https://xxxx.up.railway.app/privacy` 를 넣어두면 나중에 라이브 전환 때 편합니다.

> 웹훅 서명이 두 시크릿 중 어느 쪽으로 오든 서버가 둘 다 검사하므로, 둘 다 넣어두면 안전합니다.

### 3-4. 재배포 확인
Variables 를 바꾸면 Railway 가 자동 재배포합니다. 로그에 `▶ Instagram AutoDM 서버 시작` 이 다시 뜨면 완료.

### 3-5. 앱 게시 (라이브 전환) — 웹훅을 받으려면 필요
Instagram API 설정 페이지의 Webhooks 섹션에 **"Webhooks를 수신하려면 앱이 공개 상태여야 합니다"** 라고 적혀 있습니다.
공개(라이브)로 바꾸더라도 검수 전에는 **앱에 역할이 있는 계정(관리자/테스터)만** 쓸 수 있으므로 본인 계정용으로는 충분합니다.
게시 전 필수 입력 (앱 설정 → 기본 설정):
- **개인정보처리방침 URL**: `https://xxxx.up.railway.app/privacy`
- **사용자 데이터 삭제**: 데이터 삭제 안내 URL 또는 콜백 `https://xxxx.up.railway.app/auth/instagram/data-deletion`
- **앱 아이콘 1024×1024** (PNG 아무 이미지, 예: 그로우써클 로고)
- 카테고리 선택
그 다음 왼쪽 메뉴 **게시(Publish)** 에서 앱을 게시(라이브)하세요. 게시가 막히면 "제출 자격 없음: … 누락" 메시지에 무엇이 빠졌는지 나옵니다.
게시 전에는 `COMMENT_POLLING=1` 폴링으로 댓글은 잡을 수 있지만, 버튼 클릭(팔로우 확인) 알림은 웹훅이 있어야 하므로 게시는 꼭 필요합니다.

---

## ④ 대시보드에서 인스타그램 연결

1. `https://xxxx.up.railway.app/#connect` → **Instagram 으로 연결** → 인스타그램 로그인 → 권한 3개 허용.
2. 돌아오면 사이드바에 `@내계정 · 웹훅 구독됨 · 토큰 59일 남음` 이 보입니다.
   (이 순간 서버가 `/subscribed_apps` 호출로 **계정 단위 웹훅 구독**까지 자동 처리합니다. "웹훅 미구독"이면 **웹훅 재구독** 버튼)
3. 인스타그램 앱에서 **설정 → 메시지 및 스토리 답장 → 메시지 요청 → "메시지 접근 허용"** 이 켜져 있는지 다시 확인.

---

## ⑤ 첫 자동화 만들고 테스트

1. **자동 DM & 대댓글 → + 자동화 추가**
   - 게시물: 테스트할 릴스 하나 선택
   - 키워드: `테스트` (포함)
   - DM 종류: 버튼형 / 제목·부제목 입력 / 버튼 레이블 `자료 받기` / 클릭 시 메시지에 리드마그넷 링크
   - 🔒 팔로워에게만 공개: 켬
2. **다른 인스타그램 계정**(가족/지인 계정, 또는 부계정)으로 그 릴스에 `테스트` 댓글.
   본인 계정 댓글은 무시되도록 되어 있습니다.
3. 몇 초 안에 대시보드 **활동 로그**에 `comment_matched → dm_sent` 가 찍히고, 댓글 단 계정에 카드 DM 이 옵니다.
   (팔로우 안 한 계정이면 "요청" 폴더에 도착)
4. 카드의 버튼을 누르면:
   - 팔로우 안 한 계정 → "팔로우 해주셨다면 아래 버튼을…" + **[팔로우했어요.]** 버튼 (로그 `gate_blocked`)
   - 팔로우 후 [팔로우했어요.] → 링크 도착 (로그 `delivered`, 대시보드 "팔로우 후 전환" +1)
5. 5~7분 뒤 댓글 아래 자동 대댓글이 달립니다 (`comment_reply`).

### 웹훅이 안 올 때
- 앱이 **개발 모드**면 테스터로 등록된 계정의 게시물만 알림이 옵니다. 댓글 다는 쪽은 아무 계정이나 상관없음.
- 그래도 `comment_matched` 가 안 찍히면 Railway Variables 에 `COMMENT_POLLING=1` 을 넣으세요. 2분마다 최근 게시물 댓글을 직접 읽어 같은 흐름을 탑니다. (버튼 클릭 알림 `messaging_postbacks` 는 폴링으로 대체할 수 없으니 메시지 웹훅은 꼭 살아 있어야 합니다)
- 로그에 `webhook_signature` 오류가 있으면 `IG_APP_SECRET` / `META_APP_SECRET` 값을 다시 확인.

### 다른 사람 계정도 연결해 서비스하려면 (선택)
**App Review → 권한 및 기능** 에서 `instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_manage_comments` 의 **고급 액세스** 요청 + 앱 모드를 **라이브** 로. 사용 영상(스크린캐스트)과 개인정보처리방침 URL 이 필요합니다. 본인 계정만 쓰면 불필요.

---

## 대안 A. Fly.io (CLI 익숙하면)

```bash
brew install flyctl && fly auth login
cd instagram-autodm
fly launch --no-deploy            # 앱 이름/리전(nrt=도쿄) 선택, Dockerfile 자동 인식
fly volumes create autodm_data --size 1 --region nrt
```
`fly.toml` 에 추가:
```toml
[mounts]
  source = "autodm_data"
  destination = "/app/data"
[http_service]
  internal_port = 3000
  auto_stop_machines = "off"      # 잠들면 웹훅을 놓침
  min_machines_running = 1
```
```bash
fly secrets set IG_APP_ID=... IG_APP_SECRET=... META_APP_SECRET=... WEBHOOK_VERIFY_TOKEN=... DASHBOARD_PASSWORD=... PUBLIC_URL=https://<앱이름>.fly.dev
fly deploy
```

## 대안 B. Render
Web Service → 저장소 연결 → Root Directory `instagram-autodm` → Runtime: Docker → **Starter 이상 유료 플랜** (무료 플랜은 15분 후 잠들고 디스크가 없어 부적합) → Disks 에서 `/app/data` 1GB 추가 → 환경 변수 입력 → 생성된 `https://xxx.onrender.com` 을 `PUBLIC_URL` 로.

## 대안 C. 내 Mac 에서 상시 실행 + 터널 (무료, Mac 이 항상 켜져 있어야 함)
```bash
cd instagram-autodm && cp .env.example .env   # 값 채우기
npm start
# 다른 터미널에서
brew install ngrok && ngrok http 3000          # 무료 계정은 주소가 매번 바뀜 → 고정 도메인은 유료
```
고정 주소가 필요하면 Cloudflare Tunnel(`cloudflared tunnel --url http://localhost:3000`, 본인 도메인 연결 시 무료 고정)을 쓰세요.
ngrok 무료 주소는 재시작마다 바뀌므로 Meta 앱의 주소들도 매번 바꿔야 해서 **테스트용**으로만 권장합니다.
