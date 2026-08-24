"""오케스트레이터 공통 설정 - 환경 변수 한 곳에서 관리"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# 카드 저장소 = 옵시디언 볼트 하나 (노션 철수 완료). 볼트 경로는 DG_VAULT_ROOT(기본 vault/).
# 볼트 동기화는 GitHub Actions가 vault/를 커밋·push하는 git/GitHub 단일 경로다.
# 승인 대기·발행 알림은 텔레그램으로 나간다 (obsidian_state.notify → telegram_notify).

# Manus (선택 - 외부 리서치 전담, 없으면 Claude 리서치로 폴백)
MANUS_API_KEY = os.getenv("MANUS_API_KEY", "")
MANUS_API_BASE = os.getenv("MANUS_API_BASE", "https://api.manus.ai")

# 모델 (유틸리티/글쓰기 분리)
MODEL_UTILITY = os.getenv("DG_MODEL_UTILITY", "claude-sonnet-5")
MODEL_WRITING = os.getenv("DG_MODEL_WRITING", "claude-opus-4-8")

# 에이전트 토론 라운드 제한 (끝없는 대화 방지)
DIALOGUE_MAX_ROUNDS = int(os.getenv("DG_DIALOGUE_MAX_ROUNDS", "2"))

# 교육윤리 검수가 revise를 내면 검수 피드백을 작가에게 되먹여 재작성하는 최대 라운드.
# 0이면 재작성 없이 기존처럼 사람에게 넘긴다(검수 revise → approval/needs_human).
ETHICS_MAX_ROUNDS = int(os.getenv("DG_ETHICS_MAX_ROUNDS", "2"))

# 한 번의 cron 실행에서 처리할 최대 카드 수 (rate limit 보호)
MAX_CARDS_PER_RUN = int(os.getenv("DG_MAX_CARDS_PER_RUN", "5"))

# brief/draft 단계에서 running으로 이만큼 분을 넘기면 중간 크래시로 보고 재큐한다.
# (Actions 타임아웃/OOM으로 초안 생성이 끊긴 고아 카드가 영구히 방치되지 않게)
STALE_RUNNING_MINUTES = int(os.getenv("DG_STALE_RUNNING_MINUTES", "60"))

# 글 평가(50점) 총점이 이 값 이상이면 평가표 2차안(전문 재작성) 호출을 생략한다.
# 좋은 초안에 굳이 비싼 재작성을 돌리지 않기 위한 토큰 절감 게이트. 0이면 항상 생성.
RUBRIC_SKIP_QUALITY = int(os.getenv("DG_RUBRIC_SKIP_QUALITY", "45"))

# 키워드 자동 승인: 최고점 키워드를 사람 승인 없이 자동 채택 → 초안까지 자동 진행.
# 사람 병목을 줄이기 위해 기본 ON. 발행 승인 게이트만 사람이 통과시킨다.
# 끄려면 DG_AUTO_APPROVE_KEYWORD=false (또는 0/no/off). 빈 값/미설정은 ON으로 본다.
AUTO_APPROVE_KEYWORD = (
    os.getenv("DG_AUTO_APPROVE_KEYWORD", "").strip().lower()
    not in ("0", "false", "no", "off")
)

# 기본 발행 예약 시각(KST, 'HH:MM'). 설정하면 발행 승인 시 publish_at이 비어 있는
# 카드에 다음 도래하는 그 시각을 자동 기입한다(카드에 남아 사람이 고치거나 지울 수 있음).
# 비워두면(기본) 예전처럼 승인 직후 첫 실행에서 바로 발행한다.
DEFAULT_PUBLISH_TIME = os.getenv("DG_DEFAULT_PUBLISH_TIME", "").strip()

# 릴스(숏폼) 영상 생성 — Open Generative AI의 백엔드 게이트웨이 Muapi.ai 사용
# (설치/키 발급: docs/open-generative-ai-setup.md). 키가 없으면 --dry-run만 가능.
# 워크플로우가 미설정 시크릿을 빈 문자열로 넘기므로 `or` 폴백 필수 (#58과 같은 패턴 —
# 빈 모델명이면 POST /api/v1/ 로 나가 404 "Not Found"가 났다).
MUAPI_API_KEY = os.getenv("MUAPI_API_KEY", "")
REELS_VIDEO_MODEL = os.getenv("DG_REELS_VIDEO_MODEL") or "seedance-lite-t2v"
REELS_VIDEO_RESOLUTION = os.getenv("DG_REELS_VIDEO_RESOLUTION") or "720p"
REELS_SCENE_SECONDS = int(os.getenv("DG_REELS_SCENE_SECONDS", "5") or "5")
REELS_MAX_SCENES = int(os.getenv("DG_REELS_MAX_SCENES", "7") or "7")
