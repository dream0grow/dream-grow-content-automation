# aside CLI — 클라우드 세션 설치 가이드

목표: 어떤 컴퓨터에서 접속하든, 클라우드(Claude Code on the web) 세션 안에서
`aside` CLI를 쓸 수 있게 한다.

참고: aside는 CI 확인·릴리스 증적 수집·브라우저 자동화용 CLI다
(공식 문서: https://docs.aside.com/help/developers).

## 왜 "한 번 설치"로는 안 되나

클라우드 세션은 매번 **새 컨테이너**에서 시작하고, 세션이 끝나면 컨테이너가 사라진다.
그래서 지금 설치해도 다음 세션엔 없다. 두 가지를 갖춰야 한다.

1. **네트워크 허용** — 설치 파일을 받는 `releases.aside.com` 도메인이
   환경(environment)의 네트워크 정책에서 허용돼야 한다. (1회 설정, 사용자만 가능)
2. **세션마다 자동 설치** — 저장소에 든 설치 스크립트가 세션 시작 때 돌게 한다.

## 1단계 — 네트워크 정책에 도메인 허용 (사용자 1회 작업)

현재 이 환경은 `releases.aside.com` 접속이 403으로 차단돼 있다.

1. 브라우저에서 https://claude.ai/code 접속
2. 좌측(또는 설정)에서 **Environments** → 이 저장소가 쓰는 환경 선택
3. **Network policy**(네트워크 정책) 항목에서 허용 도메인에 추가:
   - `releases.aside.com` (설치 파일)
   - `api.aside.com` (CLI가 서버와 통신할 때 — aside 문서 기준으로 필요 시)
4. 저장 후 **새 세션**을 시작해야 적용된다.

자세한 동작은 https://code.claude.com/docs/en/claude-code-on-the-web 참고.

## 2단계 — 설치 스크립트 실행

이 저장소에 설치 스크립트가 들어 있다: `tools/install_aside.sh`

- 이미 설치돼 있으면 그냥 통과(여러 번 실행해도 안전)
- 공식 설치 스크립트를 파일로 받아 실행
- 네트워크가 막혀 있으면 원인과 해결 방법을 출력

수동 실행:

```bash
bash tools/install_aside.sh
aside --version   # 설치 확인
```

## 3단계 — 세션 시작 때 자동 실행 (SessionStart 훅)

세션마다 손으로 실행하지 않으려면 SessionStart 훅을 등록한다.
`.claude/settings.json`에 아래를 추가하면 된다(파일이 없으면 새로 만든다).

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/tools/install_aside.sh\" || true"
          }
        ]
      }
    ]
  }
}
```

- `|| true` 덕분에 네트워크가 아직 막혀 있어도 세션 시작을 막지 않는다.
- 이 설정이 **main에 머지된 뒤** 시작하는 세션부터 적용된다.
- 보안 주의: 훅은 세션 시작 때 자동 실행되므로, 스크립트 내용을 확인하고
  넣는다(이 스크립트는 aside 공식 설치 스크립트만 받아 실행한다).

## 4단계 — 로그인/인증 (필요 시)

CLI가 계정 인증을 요구하면(대부분의 SaaS CLI가 그렇다):

1. aside 개발자 설정 페이지에서 API 키/토큰 발급 (docs.aside.com 참고)
2. claude.ai/code 환경 설정의 **환경 변수(Environment variables)**에 등록
   (예: `ASIDE_API_KEY` — 실제 변수 이름은 aside 문서 확인)
3. 새 세션부터 CLI가 그 키를 읽어 인증된다.

키를 저장소에 커밋하지 말 것 — 반드시 환경 변수/시크릿으로만 넣는다.

## 요약 체크리스트

- [ ] claude.ai/code 환경 네트워크 정책에 `releases.aside.com` 허용 추가
- [ ] 새 세션에서 `bash tools/install_aside.sh` 실행 → `aside --version` 확인
- [ ] `.claude/settings.json`에 SessionStart 훅 추가 (위 JSON)
- [ ] (필요 시) aside API 키를 환경 변수로 등록
- [ ] 브랜치를 main에 머지 → 이후 모든 세션에서 자동 설치
