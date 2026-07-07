"""매일 새 콘텐츠 주제를 자동 발제해 intake 카드를 만든다.

GitHub Actions가 하루 1회 실행(daily-intake.yml). 기존 카드 제목을 중복 회피 목록으로
넘겨 Claude가 새 주제 N개를 제안하고, 각각을 intake/queued 카드로 생성한다.
이후는 오케스트레이터(orchestrator.run)가 리서치 → 키워드(자동 승인) → 브리프 →
토론 초안 → 검수까지 자동 진행하고, 초안이 완성되면 텔레그램으로 알린다.
사람은 마지막 '발행 승인'만 하면 된다.

실행:
  python3 -m orchestrator.daily_intake
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import llm, prompts
from orchestrator import state as store

# 하루에 만들 주제 수 (기본 1개 = 매일 글 1편)
DAILY_TOPIC_COUNT = int(os.getenv("DG_DAILY_TOPIC_COUNT", "1"))
DEFAULT_AUDIENCE = os.getenv("DG_DEFAULT_AUDIENCE", "초등 저학년 학부모")


def log(msg: str):
    print(f"[daily-intake] {msg}", flush=True)


def _existing_topics() -> list[str]:
    """중복 회피용: 현재 DB에 있는 카드 제목을 모은다(최근 100개)."""
    try:
        cards = store.query_cards(page_size=100)
    except Exception as e:
        log(f"기존 카드 조회 실패(중복 회피 없이 진행): {e}")
        return []
    return [c["topic"] for c in cards if c.get("topic")]


def run():
    store.require_backend()
    existing = _existing_topics()
    existing_block = "\n".join(f"- {t}" for t in existing[:120]) or "(없음)"

    ideas = llm.call_json(
        prompts.TOPIC_IDEAS.format(
            count=DAILY_TOPIC_COUNT,
            audience=DEFAULT_AUDIENCE,
            existing=existing_block,
        ),
        system=prompts.get_system(),
    )
    topics = ideas.get("topics", [])[:DAILY_TOPIC_COUNT]
    if not topics:
        log("발제된 주제가 없어 종료")
        return

    seen = {t.strip() for t in existing}
    created = 0
    for t in topics:
        title = (t.get("topic") or "").strip()
        if not title or title in seen:
            log(f"건너뜀(빈 제목/중복): {title!r}")
            continue
        audience = (t.get("audience") or DEFAULT_AUDIENCE).strip()
        try:
            page_id = store.create_card(title, audience=audience)
        except Exception as e:
            log(f"카드 생성 실패: {title} — {e}")
            continue
        seen.add(title)
        created += 1
        log(f"카드 생성: {title} ({audience}) → {page_id}")

    log(f"완료: {created}개 intake 카드 생성 (오케스트레이터가 이후 자동 진행)")


if __name__ == "__main__":
    run()
