---
title: 모바일 워크플로우 셋업 가이드
created: 2026-05-30
status: 진행중
---

# 📱 Mobile-Ready Claude Code Workflow 셋업 가이드

## 🎯 목표

맥북을 닫아두고도 핸드폰으로 Claude Code 작업을 이어가는 환경을 만든다.

## ✅ 이미 완료된 셋업

- [x] **Git 저장소 초기화** (옵시디언 초생산 vault, 커밋 ca1d365)
- [x] **.gitignore 설정** (macOS, 옵시디언 캐시, 임시 파일 제외)
- [x] **자동 백업 launchd** (`com.dreamgrow.obsidian-backup`, 매시 30분 실행)
- [x] **GitHub CLI 설치** (`gh` 명령 사용 가능)

## 📋 사용자가 직접 해야 할 단계

### 1️⃣ GitHub Private 저장소 생성 (10분)

GitHub 백업으로 클라우드 이중화. iCloud 동기화 없는 상황에서 필수.

```bash
# 1. GitHub 로그인 (브라우저로 인증)
gh auth login
# → GitHub.com 선택
# → HTTPS 선택
# → "Y" (gh를 git credential helper로)
# → Login with a web browser 선택
# → 화면에 나온 코드를 브라우저에서 입력

# 2. Private 저장소 생성 + 푸시
cd "/Users/lhg/Documents/obsidian/초생산"
gh repo create obsidian-chosaengsan --private --source=. --remote=origin --push
```

이후 `auto-backup.sh`가 매시 30분 자동으로 GitHub에도 푸시.

### 2️⃣ Tailscale 설치 (15분, 무료)

맥북과 iPhone 사이 안전한 사설 VPN.

**맥북**:
```bash
brew install --cask tailscale
```
- 설치 후 메뉴바 아이콘 클릭 → 로그인 (Google/Microsoft/이메일)

**iPhone**:
- App Store에서 "Tailscale" 검색 → 설치
- 같은 계정으로 로그인
- VPN 권한 허용

설치 후 양쪽 디바이스가 같은 Tailnet에 자동 연결. `100.x.x.x` 사설 IP 부여됨.

### 3️⃣ 맥북 SSH 서버 활성화 (5분)

```bash
sudo systemsetup -setremotelogin on
# 또는 시스템 설정 → 일반 → 공유 → "원격 로그인" 켜기
```

권한 설정: 원격 로그인 권한을 본인 계정에 한정.

### 4️⃣ 맥북 클램쉘 모드 (10분, 일회 셋업)

맥북 lid를 닫고도 작동하게 만들기.

**필수 조건**:
- 전원 어댑터 연결 (전원 끊기면 잠자기)
- 외부 디스플레이 또는 **HDMI 더미 동글** (~$8, 쿠팡/알리)

**또는 디스플레이 없이도 작동시키는 법**:
```bash
# 잠자기 영구 비활성화 (전원 연결 시)
sudo pmset -c sleep 0 disksleep 0 displaysleep 30

# 즉시 잠자기 방지 (테스트용)
caffeinate -dimsu &
```

### 5️⃣ iPhone SSH 클라이언트 설치 (5분)

**무료**: Termius
- App Store → "Termius" 설치
- New Host 추가:
  - Hostname: `lhg-macbook` (Tailscale에서 보이는 맥북 이름)
  - Username: `lhg`
  - Password 또는 SSH Key

**유료 추천**: Blink Shell ($20, 일회 결제)
- mosh 지원으로 연결 끊겨도 자동 복구
- 빠른 키보드 단축키
- 멀티 탭

### 6️⃣ 첫 모바일 접속 테스트

iPhone에서:
1. Tailscale 켜기 (자동 연결)
2. Termius/Blink 실행
3. SSH 접속:
   ```bash
   ssh lhg@100.x.x.x  # Tailscale IP
   # 또는
   ssh lhg@lhg-macbook
   ```
4. 작업 디렉토리 이동:
   ```bash
   cd "/Users/lhg/Library/CloudStorage/GoogleDrive-leehg0211@gmail.com/내 드라이브/ㄱ.클로드코드_드림그로우"
   ```
5. Claude Code 실행:
   ```bash
   claude
   ```

---

## 🔄 일상 사용 시나리오

### 시나리오 1: 카페에서 콘텐츠 리뷰
1. iPhone Tailscale 켜기
2. Termius로 맥북 SSH
3. `cd` + `claude` 실행
4. "오늘 발행할 글 확인해줘" 명령
5. 리뷰 + 수정 + 발행시간 지정
6. SSH 종료 → cron이 알아서 발행

### 시나리오 2: 출퇴근 중 아이디어 입력
1. iPhone에서 옵시디언 앱 사용 (vault sync 별도 설정 필요)
2. 또는 SSH로 맥북 접속해서 직접 파일 작성

### 시나리오 3: 자동 백업 확인
```bash
tail -20 /tmp/obsidian-git-backup.log
```

---

## 📊 백업 현황 (Phase 1 완료 후)

| 백업 위치 | 자동/수동 | 빈도 |
|---------|---------|------|
| 로컬 (`~/Documents/obsidian/초생산`) | 수동 | 작업 시 |
| Git 로컬 (`.git/`) | 자동 | 매시 30분 |
| GitHub Private | 자동 (gh 인증 후) | 매시 30분 |
| Google Drive (작업 폴더) | 자동 | 실시간 |

**3중 백업으로 데이터 안전 확보** ✅

---

## 💰 비용 합계

| 항목 | 비용 | 비고 |
|------|------|------|
| Tailscale | $0/월 | 개인 사용 무료 |
| Termius (무료) | $0 | 기본 기능 충분 |
| GitHub Free | $0/월 | Private repo 무제한 |
| HDMI 더미 동글 | $8 | 일회성 (선택) |
| Blink Shell | $20 | 일회성 (선택, 추천) |
| **총 추가 비용** | **₩0/월 + $8~28 일회** | |

---

## 🚀 자동화 확대 다음 단계

### 가능한 추가 자동화
1. **모바일 즉시 콘텐츠 트리거** (텔레그램 bot → 맥북)
2. **발행 후 reach 데이터 수집** (Threads API)
3. **Honcho 학습 강화** (모바일에서 즉시 reflection 입력)
4. **음성 메모 → 자동 콘텐츠 변환** (모바일 녹음 → 맥북 자동 텍스트 변환 + 콘텐츠 초안)

각각 별도 셋업 가능. 현재 6개 launchd 작업 + 1개 백업 = 7개 자동화 작동 중.

---

## 🛟 문제 발생 시

### Git 백업 멈춤
```bash
launchctl list | grep obsidian
tail -50 /tmp/obsidian-backup-stderr.log
```

### Tailscale 연결 안 됨
- 양쪽 디바이스 같은 계정인지 확인
- 네트워크 변경 (WiFi → LTE) 시 재연결 필요할 수 있음

### SSH 접속 거부
```bash
# 맥북에서 SSH 상태 확인
sudo systemsetup -getremotelogin
# 방화벽 확인
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --listapps | grep sshd
```

---

작성: 2026-05-30
다음 업데이트: 사용자 셋업 진행 결과 반영
