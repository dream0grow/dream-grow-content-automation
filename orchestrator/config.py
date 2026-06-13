"""오케스트레이터 공통 설정 - 환경 변수 한 곳에서 관리"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# 노션 (필수)
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_PIPELINE_DB_ID = os.getenv("NOTION_PIPELINE_DB_ID", "")
NOTION_VERSION = "2022-06-28"
# 승인 대기 시 멘션할 노션 사용자 ID (비우면 멘션 없이 댓글만). 노션 알림 발송용.
NOTION_MENTION_USER_ID = os.getenv("NOTION_MENTION_USER_ID", "")

# Manus (선택 - 외부 리서치 전담, 없으면 Claude 리서치로 폴백)
MANUS_API_KEY = os.getenv("MANUS_API_KEY", "")
MANUS_API_BASE = os.getenv("MANUS_API_BASE", "https://api.manus.ai")

# 모델 (유틸리티/글쓰기 분리)
MODEL_UTILITY = os.getenv("DG_MODEL_UTILITY", "claude-sonnet-4-6")
MODEL_WRITING = os.getenv("DG_MODEL_WRITING", "claude-opus-4-8")

# 에이전트 토론 라운드 제한 (끝없는 대화 방지)
DIALOGUE_MAX_ROUNDS = int(os.getenv("DG_DIALOGUE_MAX_ROUNDS", "2"))

# 한 번의 cron 실행에서 처리할 최대 카드 수 (rate limit 보호)
MAX_CARDS_PER_RUN = int(os.getenv("DG_MAX_CARDS_PER_RUN", "5"))

# 키워드 자동 승인: true면 최고점 키워드를 사람 승인 없이 자동 채택 (대량 검토용 초안 생성).
# 발행 승인 게이트는 그대로 사람이 통과시킨다.
AUTO_APPROVE_KEYWORD = os.getenv("DG_AUTO_APPROVE_KEYWORD", "").lower() in ("1", "true", "yes", "on")


def require_notion():
    """노션 설정이 없으면 명확한 에러로 중단한다."""
    missing = []
    if not NOTION_API_KEY:
        missing.append("NOTION_API_KEY")
    if not NOTION_PIPELINE_DB_ID:
        missing.append("NOTION_PIPELINE_DB_ID")
    if missing:
        raise RuntimeError(
            f"환경 변수 누락: {', '.join(missing)} (.env 또는 GitHub Secrets에 설정)"
        )
