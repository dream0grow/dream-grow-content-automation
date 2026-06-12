"""YouTube 자동화 설정.

경로, 채널 레지스트리, API 키, 상수.
환경변수는 content-automation/.env 에서 로드한다.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ============================================================
# 경로
# ============================================================

CONTENT_AUTOMATION_DIR = Path(__file__).resolve().parent.parent
YOUTUBE_DIR = CONTENT_AUTOMATION_DIR / "youtube"
ASSETS_DIR = YOUTUBE_DIR / "assets"
MEMES_DIR = ASSETS_DIR / "memes"
SFX_DIR = ASSETS_DIR / "sfx"
TEMPLATES_DIR = ASSETS_DIR / "templates"

OBSIDIAN_VAULT = Path("/Users/lhg/Documents/obsidian/초생산")
RAW_PAPERS_DIR = OBSIDIAN_VAULT / "raw" / "papers"
ZETTELKASTEN_MEMO_DIR = OBSIDIAN_VAULT / "제텔카스텐" / "5. 제텔카스텐" / "1단계 - 메모"

SNS_SYSTEM_DIR = OBSIDIAN_VAULT / "SNS 콘텐츠 제작 시스템"
SCRIPTS_BASE_DIR = SNS_SYSTEM_DIR / "06 제작" / "52 원고"
VIDEO_PRODUCTION_BASE_DIR = SNS_SYSTEM_DIR / "06 제작" / "55 영상제작"

# 로컬 전용 (Dropbox 동기화 제외 권장)
LOCAL_VIDEO_OUTPUT = Path.home() / "YouTubeAutomation" / "output"

# 피드백 DB
FEEDBACK_DB_PATH = YOUTUBE_DIR / "feedback_db.json"

# ============================================================
# 채널 레지스트리 (실수 방지를 위한 핵심 안전장치)
# ============================================================

CHANNELS = {
    "dream_grow": {
        "code": "DG",
        "name": "Dream_Grow",
        "id": "",  # YouTube 채널 ID (나중에 설정)
        "oauth_token": "dg_token.json",
        "upload_enabled": False,  # 수동 업로드 채널
        "target": "초등 자녀 부모 (30~45세)",
        "script_dir_name": "DG",
    },
    "story_maker": {
        "code": "SM",
        "name": "Story Maker",
        "id": "",
        "oauth_token": "sm_token.json",
        "upload_enabled": False,
        "target": "스토리 애호가",
        "script_dir_name": "SM",
    },
    "science_channel": {
        "code": "SC",
        "name": "Science Channel",  # 채널명 미정
        "id": "",  # 채널 개설 후 기입
        "oauth_token": "sc_token.json",
        "upload_enabled": True,  # 이 채널만 자동 업로드
        "target": "과학/자기계발 관심 일반 대중",
        "script_dir_name": "SC",
    },
}

DEFAULT_CHANNEL = "science_channel"


def get_channel(brand: str) -> dict:
    """채널 브랜드 키로 설정을 조회. 없으면 KeyError."""
    if brand not in CHANNELS:
        raise KeyError(f"Unknown channel brand: {brand}. Known: {list(CHANNELS)}")
    return CHANNELS[brand]


def get_scripts_dir(brand: str) -> Path:
    """채널별 원고 저장 경로."""
    return SCRIPTS_BASE_DIR / get_channel(brand)["script_dir_name"]


def get_video_dir(brand: str) -> Path:
    """채널별 영상 제작 경로."""
    return VIDEO_PRODUCTION_BASE_DIR / get_channel(brand)["script_dir_name"]


# ============================================================
# API 키
# ============================================================

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")  # 선택 (무료)
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY", "")
TENOR_API_KEY = os.getenv("TENOR_API_KEY", "")
FREESOUND_API_KEY = os.getenv("FREESOUND_API_KEY", "")

YOUTUBE_SPREADSHEET_ID = os.getenv(
    "YOUTUBE_SPREADSHEET_ID",
    "1H3KPTJ5RsA7PdSViia9c9buaPbVg_trXq8EtpUh8ldU",
)

SHEETS_CREDENTIALS = CONTENT_AUTOMATION_DIR / "gcp_sheets_credentials.json"
SHEETS_TOKEN = CONTENT_AUTOMATION_DIR / "gcp_sheets_token.json"

# ============================================================
# 모델 및 생성 설정
# ============================================================

CLAUDE_MODEL = "claude-sonnet-4-20250514"
SCRIPT_MAX_TOKENS = 8000
TARGET_VIDEO_LENGTH_MIN = 10  # 분
TTS_VOICE_KO = "ko-KR-SunHiNeural"  # 대안: ko-KR-InJoonNeural

# ============================================================
# Sheets 탭 이름
# ============================================================

TAB_TRIGGER = "SC_트리거"
TAB_METRICS = "SC_성과"
TAB_INSIGHTS = "SC_인사이트"

# ============================================================
# 자동 승격 임계값
# ============================================================

PROMOTION_AUTO_THRESHOLD = 0.8
PROMOTION_REVIEW_THRESHOLD = 0.5
