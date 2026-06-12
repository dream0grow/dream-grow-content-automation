"""도메인 상수 - 레거시 calendar_scheduler.py / thread_generator.py에서 포팅"""
import enum


class ContentType(str, enum.Enum):
    thread = "thread"
    reels = "reels"
    newsletter = "newsletter"


class ContentStatus(str, enum.Enum):
    review_wait = "리뷰대기"
    review_done = "리뷰완료"
    publish_wait = "발행대기"
    published = "발행완료"
    failed = "실패"


class JobKind(str, enum.Enum):
    thread = "thread"
    reels = "reels"
    newsletter = "newsletter"
    publish = "publish"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


# 허용된 상태 전이 (서비스 계층에서 강제)
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ContentStatus.review_wait.value: {ContentStatus.review_done.value},
    ContentStatus.review_done.value: {
        ContentStatus.publish_wait.value,
        ContentStatus.review_wait.value,
        ContentStatus.published.value,  # 즉시 발행
        ContentStatus.failed.value,
    },
    ContentStatus.publish_wait.value: {
        ContentStatus.published.value,
        ContentStatus.failed.value,
        ContentStatus.review_wait.value,  # 되돌리기 (예약 해제)
        ContentStatus.review_done.value,  # 예약만 해제
    },
    ContentStatus.failed.value: {
        ContentStatus.review_wait.value,
        ContentStatus.publish_wait.value,
        ContentStatus.published.value,  # 재발행 성공
    },
    ContentStatus.published.value: set(),
}

# 하루 중 발행 가능한 시간대 (KST) - 레거시와 동일
PUBLISH_HOURS: list[tuple[int, int]] = [(7, 10), (17, 50), (20, 50)]
MAX_PER_DAY = 3
SCHEDULE_DAYS = 7

WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]

# 카테고리 정규화 맵 (레거시 calendar_scheduler.py와 동일)
CATEGORY_MAP = {
    "독서읽기": "독서", "독서": "독서",
    "수학": "수학", "수학연산": "수학",
    "훈육": "훈육", "훈육지도": "훈육", "훈육, 감정": "훈육",
    "감정/심리": "감정", "뇌발달심리": "감정", "감정": "감정",
    "학습": "학습", "습관루틴": "학습", "수학, 학습": "학습",
    "미디어/AI": "미디어", "미디어": "미디어", "영어": "학습",
    "놀이": "놀이",
    "학교생활": "학교", "학부모소통": "학교", "학교": "학교",
    "크리에이터": "크리에이터",
}

ALL_CATEGORIES = ["훈육", "수학", "독서", "미디어", "놀이", "감정", "학습", "학교", "크리에이터"]

# Threads 글자 제한
THREADS_HARD_LIMIT = 500   # API 제한
THREADS_STYLE_LIMIT = 280  # 하우스 스타일 권장


def normalize_category(raw: str) -> str:
    return CATEGORY_MAP.get(raw, raw)
