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
