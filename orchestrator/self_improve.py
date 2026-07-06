"""자가 학습 루프 (헤르메스 스타일, 결정 #6)

주 1회 실행. Honcho에 쌓인 사용자 수정 패턴 + 팀 학습 + 발행 성과를 분석해
프롬프트 개선안을 노션 큐시트(승인 대기 카드)로 제출한다.

- 제안까지만 자동. 사람이 카드에서 approval_status=approved로 바꾸면
  apply_approved()가 개선안을 Honcho approved-prompt-overlay에 승격하고,
  이후 모든 에이전트 호출(prompts.get_system)에 자동 반영된다.

실행:
  python3 -m orchestrator.self_improve            # 회고 → 큐시트 제출
  python3 -m orchestrator.self_improve --apply    # 승인된 큐시트 반영
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import llm, prompts
from orchestrator import state as notion_state

QUEUE_STAGE = "analysis"  # 큐시트 카드는 analysis stage로 구분
QUEUE_PREFIX = "[큐시트] 프롬프트 개선안"


def _collect_honcho() -> tuple[str, str]:
    """기존 Honcho 메모리에서 수정 패턴과 팀 학습을 모은다 (결정 #2 통합)."""
    try:
        from memory_manager import get_honcho_client, get_team_learnings
        from diff_learner import get_correction_context
        client = get_honcho_client()
        if not client:
            return "", ""
        corrections, learnings = [], []
        for channel in ["thread", "reels", "newsletter", "blog"]:
            c = get_correction_context(client, channel)
            if c:
                corrections.append(f"[{channel}]\n{c}")
            t = get_team_learnings(client, channel)
            if t:
                learnings.append(f"[{channel}]\n{t}")
        return "\n\n".join(corrections), "\n\n".join(learnings)
    except Exception as e:
        print(f"Honcho 수집 실패 (계속 진행): {e}")
        return "", ""


def _collect_performance() -> str:
    """노션의 published 카드에서 성과 메모를 모은다."""
    lines = []
    for card in notion_state.query_cards(stage="published", page_size=10):
        body = notion_state.read_sections(card["page_id"])
        lines.append(f"- {card['topic']} ({card['content_id']})\n{body[:1500]}")
    return "\n\n".join(lines)


def retrospect():
    """회고 실행 → 개선안 큐시트 카드를 노션에 생성한다."""
    notion_state.require_backend()
    corrections, learnings = _collect_honcho()
    performance = _collect_performance()
    if not any([corrections, learnings, performance]):
        print("분석할 학습/성과 데이터가 아직 없습니다. 종료.")
        return

    result = llm.call_json(
        prompts.SELF_IMPROVE.format(
            corrections=corrections or "(없음)",
            team_learnings=learnings or "(없음)",
            performance=performance or "(없음)",
        ),
        system=prompts.get_system(),
    )

    body = (
        f"## 회고 요약\n{result.get('summary', '')}\n\n"
        f"## 제안 지침 (승인 시 모든 에이전트 프롬프트에 반영)\n"
        + "\n".join(f"- {r}" for r in result.get("proposed_rules", []))
        + "\n\n## 사람 판단 필요 (기존 지침과 모순)\n"
        + "\n".join(f"- {c}" for c in result.get("conflicts", []) or ["없음"])
        + "\n\n## 다음 실험 제안\n"
        + "\n".join(f"- {e}" for e in result.get("next_experiments", []))
        + "\n\n---\n승인 방법: approval_status를 approved로 변경하세요. "
        "다음 self_improve --apply 실행 시 반영됩니다.\n\n"
        f"[PROPOSED_RULES_JSON]\n{json.dumps(result.get('proposed_rules', []), ensure_ascii=False)}"
    )
    page_id = notion_state.create_card(
        f"{QUEUE_PREFIX} {notion_state.next_content_id()}",
        stage=QUEUE_STAGE, status="needs_human", body=body,
    )
    notion_state.update_card(page_id, approval_status="requested")
    print(f"개선안 큐시트 제출 완료: {page_id}")


def apply_approved():
    """승인된 큐시트의 제안 지침을 Honcho approved-prompt-overlay로 승격한다."""
    notion_state.require_backend()
    cards = [
        c for c in notion_state.query_cards(
            stage=QUEUE_STAGE, approval_status="approved",
        )
        if c["topic"].startswith(QUEUE_PREFIX) and c["status"] != "done"
    ]
    if not cards:
        print("승인된 큐시트가 없습니다.")
        return
    try:
        from memory_manager import get_honcho_client
        client = get_honcho_client()
    except Exception:
        client = None
    if not client:
        print("Honcho 미설정 - 적용하려면 HONCHO_API_KEY가 필요합니다.")
        return

    user = client.peer("content-creator")
    session = client.session("approved-prompt-overlay")
    for card in cards:
        body = notion_state.read_sections(card["page_id"])
        marker = "[PROPOSED_RULES_JSON]"
        rules = []
        if marker in body:
            try:
                rules = json.loads(body.split(marker, 1)[1].strip().split("\n")[0])
            except (json.JSONDecodeError, IndexError):
                pass
        for rule in rules:
            session.add_messages([user.message(f"[승인됨 {card['topic']}] {rule}")])
        notion_state.update_card(card["page_id"], status="done")
        print(f"적용 완료: {card['topic']} ({len(rules)}개 지침)")


if __name__ == "__main__":
    if "--apply" in sys.argv:
        apply_approved()
    else:
        retrospect()
