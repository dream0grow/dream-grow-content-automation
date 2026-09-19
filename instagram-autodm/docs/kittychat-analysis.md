# KittyChat (kittychat.ai) 분석 기록

분석일: 2026-09-19 · 대상: 로그인된 대시보드(`/ko/dashboard/`, 계정 dream_on_lee, Pro 플랜) + 공개 지식베이스 + Meta 개발자 문서

## 1. 대시보드 메뉴 구조

| 메뉴 | 내용 | 본 프로젝트 반영 |
|---|---|---|
| 대시보드 | 자동DM 발송 횟수(0/∞), AI 답변 수/월(0/3000), AI 트레이닝 아이템, 결제 주기, 발송/리드 차트, 최근 업데이트(경고 로그) | ✅ 통계 카드·차트·활동 로그 |
| 자동 DM & 대댓글 | 자동화 목록(키워드 / DM 미리보기 / 상세 / 액션), 설정, 일반 자동대댓글(243개 문구), 추가/삭제 | ✅ 동일 구조 |
| 스토리 멘션 | 스토리에 태그되면 자동 DM | ❌ (범위 밖) |
| DM 첫화면 메뉴 | Conversation Starters(아이스브레이커) 최대 4개 | ❌ |
| DM 속 고정 메뉴 | Persistent Menu 최대 5개 | ❌ |
| 연결 | Instagram(재연결) / TikTok. ManyChat 등과 동시 사용 불가, 슬롯당 1개 | ✅ Instagram 만 |
| DM 속 AI챗봇 | 페르소나 프롬프트, 모를 때 답변, 환영 메시지, 데이터 업로드 | ❌ |
| 리드 수집 | 리드 목록(태그/양식 필터, Export), 리드 양식(동의 3종 + 필드 + 숏코드) | ✅ 리드 목록+CSV (양식은 미구현) |
| 계정 설정 / 고객센터 | 구독, 언어·시간대, 사용 설명, 문의 | 부분 |

## 2. 자동화 편집 폼 (필드 → 우리 스키마)

| KittyChat 폼 필드 | 값 | 우리 컬럼 |
|---|---|---|
| 자동화 종류 | 댓글→DM / DM→DM (`ppcPromocodeEvent`) | `trigger_type` |
| 게시물 선택 | 선택/전체 + 게시물 체크리스트 + "다음 발행되는 게시물에 적용" | `post_scope`, `media_ids`, `apply_to_future` |
| 키워드 | 특정/불특정 (`ppcPromocodeText`), "DM→DM 자동DM도 적용" | `keyword_mode`, `keywords`, `also_dm` |
| 댓글 자동 답장 | 일반/특정/Off + 문구 5개 textarea + AI 적용 | `comment_reply_mode`, `comment_replies` |
| 자동DM 즉시/예약 | `ppcPromocodeDelayed` + 시각 | (미구현, 즉시만) |
| DM 종류 | 텍스트/버튼 (`ppcPromocodeReplyType`) | `dm_type` |
| 텍스트 본문 (900자) | `meta` | `dm_text` |
| 헤더 이미지(1080×1080), DM 제목(80), 부제목(80) | `title`, `subtitle` | `image_url`, `title`, `subtitle` |
| **'팔로워'에게만 버튼 속 메세지 공개** | `fstatus` 체크박스 (기본 ON) | `follow_gate` |
| 버튼 1~3: 레이블 + 답장 내용(900자, [username], 링크) + AI 적용 | `btntitle1..3`, `btnreply1..3` | `buttons[{label, reply, url}]` |
| 리드 양식 (캡션/제목/설명/동의1~3/성공 메시지/필드/양식 제출 시 DM) | | (미구현) |

## 3. 설정 모달 (그대로 반영)

- '키워드' 외에 추가 텍스트나 이모티콘이 있어도 자동DM 구현: 꺼짐/켜짐 → `keyword_fuzzy`
- 비팔로워에게 보내는 메세지: "댓글 남겨주셔서 감사합니다. ^_^ 저를 팔로우 해주셨다면 아래 버튼을 클릭해주세요!" → `non_follower_message`
- 비팔로워를 위한 메세지 속, 재시도 버튼 레이블: "팔로우했어요." → `follow_retry_button_label`
- 시간당 자동 DM 전송 제한: 3600 → `dm_hour_limit` ("시스템은 시간당 허용된 DM 수에 따라 메시지 간격을 균등하게 분배")
- 현 자동대댓글 상황: 꺼짐/켜짐 → `comment_reply_enabled`
- 게시물 별 한 시간 당 허용 자동 대댓글 갯수: 4 → `comment_reply_post_hour_limit`
- 대댓글 간 최대 지연 시간(초): 600~700 → `comment_reply_delay_min/max` (우리는 300~420 기본, 권장값)
- 경고 3회 발생 시 자동 댓글 답글 끄기 → `auto_disable_on_warnings`, `warning_threshold`

## 4. 팔로우 상태 확인 기능 (지식베이스 `/ko/follow-check`)

- 버튼형 템플릿의 버튼을 클릭했을 때 팔로우 여부를 확인.
- "첫 자동 DM은 모두에게 다 발송됩니다. 그 후에 메시지 속 내용을 보거나 링크를 클릭하기 위해선 팔로우가 필요하게 됩니다."
- 팔로워 → 버튼에 연결된 메시지 표시 / 비팔로워 → '팔로우 후 메시지를 확인할 수 있습니다' 안내.
- 버튼형 템플릿 사용 시 기본 활성화, 체크 해제로 끌 수 있음.
- 실제 대시보드 경고 로그: 자동 대댓글 오류 감지 시 "자동 대댓글의 지연 설정을 5분(300초) 간격으로 설정, 3-5일 후 재활성화" 안내. 경고 2회 후 3회째 자동 비활성화.

## 5. 인스타그램 연결 방식 (연결 버튼 onclick 에서 확인)

```
https://www.instagram.com/oauth/authorize?enable_fb_login=false&force_reauth=true
  &client_id=507556081904668&response_type=code
  &scope=instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments
  &redirect_uri=https://www.kittychat.ai/fb
```
→ **Instagram API with Instagram Login** (Business Login for Instagram). Facebook 페이지 불필요. 우리도 동일하게 구현.

## 6. Meta API 근거 (개발자 문서)

- User Profile API: `GET graph.instagram.com/{IGSID}?fields=name,username,profile_pic,follower_count,is_user_follow_business,is_business_follow_user` — `is_user_follow_business` = 그 사용자가 내 계정을 팔로우하는지. 권한 `instagram_business_basic`, `instagram_business_manage_messages`.
- Private Reply: `POST /{IG_ID}/messages` `{recipient:{comment_id}, message}` — 댓글당 1회, 7일 이내, 후속 메시지는 상대가 응답한 뒤 24시간 안.
- Generic/Button 템플릿: `message.attachment.type=template`, `template_type=generic|button`, 버튼 최대 3개, `postback`(→ `messaging_postbacks` 웹훅) 또는 `web_url`.
- 대댓글: `POST /{COMMENT_ID}/replies?message=...` (`instagram_business_manage_comments`).
- 웹훅 필드: `comments`, `messages`, `messaging_postbacks`. 계정 단위 구독 `POST /{IG_ID}/subscribed_apps?subscribed_fields=...` 필수. 앱은 Live + 고급 액세스 필요(본인 계정은 테스터 역할로 개발 모드 가능).
- OAuth: `POST api.instagram.com/oauth/access_token`(단기 1시간) → `GET graph.instagram.com/access_token?grant_type=ig_exchange_token`(60일) → `GET /refresh_access_token?grant_type=ig_refresh_token`(갱신).
- 제한: Private Reply 750/시간, 텍스트 메시지 100/초.

## 7. 요금제 (참고)

Free $0(월 500 DM, 광고 삽입) / Starter $13(무제한 DM, 대댓글, 버튼형, **팔로우 확인**, [username], AI 변형) / Pro $22(2 프로필, 게시물별 대댓글, 예약 발송, 스토리 멘션, 고정 메뉴, 캐러셀, 리드 수집) / Expert $49(3 프로필, 단체 DM).
